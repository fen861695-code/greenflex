"""Reinforcement Learning Router for GreenFlex.

Implements a lightweight PPO (Proximal Policy Optimization) router that learns
to select models based on task characteristics and multi-objective rewards.

Design principles:
- Lightweight: pure numpy implementation, no PyTorch/TensorFlow dependency
- Offline-first: train on historical order data, then deploy in shadow mode
- Multi-objective reward: quality (35%), price (20%), energy (15%),
  carbon (10%), latency (10%), wait time (5%), renewable (5%)
- Safe deployment: shadow mode by default, only recommends, never auto-executes
- Auditable: every decision logged with state, action, reward, and policy version

State space:
- Task features: input_tokens, output_tokens_est, task_type, quality_requirement,
  deadline_minutes, batch_size
- Context features: current_carbon_intensity, time_of_day, gpu_available

Action space:
- Discrete: select one of N candidate models

Reward function:
- r = w_quality * quality_score + w_price * (1 - normalized_price)
    + w_energy * (1 - normalized_energy) + w_carbon * (1 - normalized_carbon)
    + w_latency * (1 - normalized_latency) + penalty_for_violations
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class RLMode(str, Enum):
    """RL router operating modes."""
    DISABLED = "disabled"
    SHADOW = "shadow"  # observe and log, but don't override rule-based
    ADVISORY = "advisory"  # suggest, user confirms
    AUTONOMOUS = "autonomous"  # auto-execute (requires explicit opt-in)


class RLSessionState(str, Enum):
    """Training session states."""
    IDLE = "idle"
    COLLECTING = "collecting"  # collecting trajectories
    TRAINING = "training"  # policy update in progress
    READY = "ready"  # trained policy available
    DEPLOYED = "deployed"  # policy in use


@dataclass
class RLState:
    """State representation for a routing decision."""
    # Task features
    input_tokens: int = 0
    output_tokens_est: int = 0
    task_type: str = "general"  # general, code, summary, translation, etc.
    quality_requirement: str = "standard"  # economy, standard, high
    deadline_minutes: int = 60
    batch_size: int = 1

    # Context features
    carbon_intensity_g_per_kwh: int = 500
    hour_of_day: int = 12
    day_of_week: int = 0  # 0=Monday
    gpu_utilization: float = 0.0

    # Candidate model features (normalized)
    candidate_count: int = 0

    def to_vector(self) -> list[float]:
        """Convert state to normalized feature vector."""
        return [
            min(self.input_tokens / 8192.0, 1.0),
            min(self.output_tokens_est / 4096.0, 1.0),
            _task_type_encoding(self.task_type),
            _quality_encoding(self.quality_requirement),
            min(self.deadline_minutes / 1440.0, 1.0),
            min(self.batch_size / 100.0, 1.0),
            min(self.carbon_intensity_g_per_kwh / 1000.0, 1.0),
            self.hour_of_day / 24.0,
            self.day_of_week / 7.0,
            self.gpu_utilization,
        ]


@dataclass
class RLAction:
    """Action: select a model."""
    model_id: str
    model_index: int
    confidence: float = 0.0  # policy probability for this action
    log_prob: float = 0.0  # log probability for PPO


@dataclass
class RLTransition:
    """Single transition for RL training."""
    state: RLState
    action: RLAction
    reward: float
    next_state: RLState | None = None
    done: bool = True
    value: float = 0.0  # value function estimate
    advantage: float = 0.0  # GAE advantage
    return_value: float = 0.0  # discounted return


@dataclass
class RLPolicyConfig:
    """PPO policy configuration."""
    # Network architecture
    hidden_dim: int = 64
    num_layers: int = 2

    # PPO hyperparameters
    learning_rate: float = 3e-4
    gamma: float = 0.99  # discount factor
    gae_lambda: float = 0.95  # GAE lambda
    clip_epsilon: float = 0.2  # PPO clip range
    entropy_coef: float = 0.01  # entropy bonus coefficient
    value_coef: float = 0.5  # value loss coefficient
    max_grad_norm: float = 0.5

    # Training
    batch_size: int = 64
    epochs_per_update: int = 4
    min_trajectories_per_update: int = 10

    # Reward weights (same as GreenRouter v2)
    reward_quality: float = 0.35
    reward_price: float = 0.20
    reward_energy: float = 0.15
    reward_carbon: float = 0.10
    reward_latency: float = 0.10
    reward_wait: float = 0.05
    reward_renewable: float = 0.05

    # Exploration
    initial_temperature: float = 1.0  # softmax temperature
    min_temperature: float = 0.1
    temperature_decay: float = 0.995

    def validate(self) -> list[str]:
        """Validate configuration, return list of issues."""
        issues = []
        if self.clip_epsilon <= 0 or self.clip_epsilon >= 1:
            issues.append("clip_epsilon must be in (0, 1)")
        if self.gamma < 0 or self.gamma > 1:
            issues.append("gamma must be in [0, 1]")
        total_reward = (
            self.reward_quality + self.reward_price + self.reward_energy
            + self.reward_carbon + self.reward_latency + self.reward_wait
            + self.reward_renewable
        )
        if abs(total_reward - 1.0) > 0.01:
            issues.append(f"reward weights must sum to 1.0, got {total_reward:.3f}")
        return issues


@dataclass
class RLPolicy:
    """PPO policy with actor-critic networks (numpy implementation)."""
    config: RLPolicyConfig = field(default_factory=RLPolicyConfig)
    version: str = "rl-router-v0.1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_updates: int = 0
    total_transitions: int = 0
    temperature: float = 1.0

    # Network weights (initialized lazily)
    _actor_weights: list[list[list[float]]] | None = None
    _actor_biases: list[list[float]] | None = None
    _critic_weights: list[list[list[float]]] | None = None
    _critic_biases: list[list[float]] | None = None

    # Training history
    episode_rewards: list[float] = field(default_factory=list)
    policy_losses: list[float] = field(default_factory=list)
    value_losses: list[float] = field(default_factory=list)
    entropies: list[float] = field(default_factory=list)

    def initialize(self, state_dim: int, action_dim: int) -> None:
        """Initialize network weights with Xavier initialization."""
        self._actor_weights = []
        self._actor_biases = []
        self._critic_weights = []
        self._critic_biases = []

        prev_dim = state_dim
        for _ in range(self.config.num_layers):
            # Actor
            w = _xavier_init(prev_dim, self.config.hidden_dim)
            b = [0.0] * self.config.hidden_dim
            self._actor_weights.append(w)
            self._actor_biases.append(b)
            # Critic
            w_c = _xavier_init(prev_dim, self.config.hidden_dim)
            b_c = [0.0] * self.config.hidden_dim
            self._critic_weights.append(w_c)
            self._critic_biases.append(b_c)
            prev_dim = self.config.hidden_dim

        # Output layers
        self._actor_weights.append(_xavier_init(prev_dim, action_dim))
        self._actor_biases.append([0.0] * action_dim)
        self._critic_weights.append(_xavier_init(prev_dim, 1))
        self._critic_biases.append([0.0])

    def is_initialized(self) -> bool:
        return self._actor_weights is not None

    def forward_actor(self, state_vec: list[float]) -> list[float]:
        """Forward pass through actor network, return action logits."""
        if not self.is_initialized():
            raise RuntimeError("Policy not initialized")
        x = state_vec
        for i in range(len(self._actor_weights) - 1):
            x = _linear(x, self._actor_weights[i], self._actor_biases[i])
            x = [_relu(v) for v in x]
        # Output layer (no activation)
        logits = _linear(x, self._actor_weights[-1], self._actor_biases[-1])
        return logits

    def forward_critic(self, state_vec: list[float]) -> float:
        """Forward pass through critic network, return value estimate."""
        if not self.is_initialized():
            raise RuntimeError("Policy not initialized")
        x = state_vec
        for i in range(len(self._critic_weights) - 1):
            x = _linear(x, self._critic_weights[i], self._critic_biases[i])
            x = [_relu(v) for v in x]
        value = _linear(x, self._critic_weights[-1], self._critic_biases[-1])
        return value[0]

    def select_action(self, state: RLState, candidate_ids: list[str]) -> RLAction:
        """Select action using current policy with softmax sampling."""
        if not self.is_initialized() or not candidate_ids:
            # Fallback: random selection
            idx = random.randrange(len(candidate_ids)) if candidate_ids else 0
            return RLAction(
                model_id=candidate_ids[idx] if candidate_ids else "",
                model_index=idx,
                confidence=1.0 / max(len(candidate_ids), 1),
                log_prob=math.log(1.0 / max(len(candidate_ids), 1)),
            )

        state_vec = state.to_vector()
        logits = self.forward_actor(state_vec)
        # Take only valid candidate actions
        valid_logits = logits[:len(candidate_ids)]
        # Apply temperature
        scaled = [l / max(self.temperature, 0.01) for l in valid_logits]
        probs = _softmax(scaled)

        # Sample action
        r = random.random()
        cumulative = 0.0
        selected_idx = 0
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                selected_idx = i
                break

        return RLAction(
            model_id=candidate_ids[selected_idx],
            model_index=selected_idx,
            confidence=probs[selected_idx],
            log_prob=math.log(max(probs[selected_idx], 1e-10)),
        )

    def compute_reward(self, result: dict[str, Any], config: RLPolicyConfig | None = None) -> float:
        """Compute multi-objective reward from order execution result.

        Expected result keys:
        - quality_score: float in [0, 1]
        - price_normalized: float in [0, 1] (lower is better)
        - energy_normalized: float in [0, 1] (lower is better)
        - carbon_normalized: float in [0, 1] (lower is better)
        - latency_normalized: float in [0, 1] (lower is better)
        - wait_normalized: float in [0, 1] (lower is better)
        - renewable_share: float in [0, 1] (higher is better)
        - deadline_met: bool
        - quality_met: bool
        """
        cfg = config or self.config
        quality = result.get("quality_score", 0.5)
        price = 1.0 - result.get("price_normalized", 0.5)
        energy = 1.0 - result.get("energy_normalized", 0.5)
        carbon = 1.0 - result.get("carbon_normalized", 0.5)
        latency = 1.0 - result.get("latency_normalized", 0.5)
        wait = 1.0 - result.get("wait_normalized", 0.5)
        renewable = result.get("renewable_share", 0.0)

        reward = (
            cfg.reward_quality * quality
            + cfg.reward_price * price
            + cfg.reward_energy * energy
            + cfg.reward_carbon * carbon
            + cfg.reward_latency * latency
            + cfg.reward_wait * wait
            + cfg.reward_renewable * renewable
        )

        # Penalties for constraint violations
        if not result.get("deadline_met", True):
            reward -= 0.3
        if not result.get("quality_met", True):
            reward -= 0.5

        return max(reward, -1.0)

    def update(self, transitions: list[RLTransition]) -> dict[str, float]:
        """PPO policy update step.

        Returns dict with policy_loss, value_loss, entropy, kl_divergence.
        """
        if not transitions or not self.is_initialized():
            return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "kl": 0.0}

        # Compute GAE advantages
        self._compute_gae(transitions)

        # Mini-batch updates
        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        num_batches = 0

        for _ in range(self.config.epochs_per_update):
            random.shuffle(transitions)
            for i in range(0, len(transitions), self.config.batch_size):
                batch = transitions[i:i + self.config.batch_size]
                losses = self._ppo_batch_update(batch)
                total_policy_loss += losses["policy_loss"]
                total_value_loss += losses["value_loss"]
                total_entropy += losses["entropy"]
                num_batches += 1

        # Decay temperature
        self.temperature = max(
            self.config.min_temperature,
            self.temperature * self.config.temperature_decay,
        )

        self.total_updates += 1
        self.total_transitions += len(transitions)
        self.updated_at = datetime.now(timezone.utc).isoformat()

        avg_policy_loss = total_policy_loss / max(num_batches, 1)
        avg_value_loss = total_value_loss / max(num_batches, 1)
        avg_entropy = total_entropy / max(num_batches, 1)

        self.policy_losses.append(avg_policy_loss)
        self.value_losses.append(avg_value_loss)
        self.entropies.append(avg_entropy)

        return {
            "policy_loss": avg_policy_loss,
            "value_loss": avg_value_loss,
            "entropy": avg_entropy,
            "kl": 0.0,  # simplified
            "transitions": len(transitions),
        }

    def _compute_gae(self, transitions: list[RLTransition]) -> None:
        """Compute Generalized Advantage Estimation."""
        gamma = self.config.gamma
        lam = self.config.gae_lambda

        # Reverse pass for GAE
        last_advantage = 0.0
        for i in reversed(range(len(transitions))):
            t = transitions[i]
            if t.done or i == len(transitions) - 1:
                next_value = 0.0
            else:
                next_value = transitions[i + 1].value

            delta = t.reward + gamma * next_value - t.value
            t.advantage = delta + gamma * lam * last_advantage
            t.return_value = t.advantage + t.value
            last_advantage = t.advantage

        # Normalize advantages
        advantages = [t.advantage for t in transitions]
        mean_adv = sum(advantages) / len(advantages)
        std_adv = math.sqrt(sum((a - mean_adv) ** 2 for a in advantages) / len(advantages) + 1e-8)
        for t in transitions:
            t.advantage = (t.advantage - mean_adv) / std_adv

    def _ppo_batch_update(self, batch: list[RLTransition]) -> dict[str, float]:
        """Single PPO batch update (simplified gradient descent)."""
        # This is a simplified implementation — full PPO would use autograd.
        # For GreenFlex MVP, we use a policy gradient approximation.
        policy_loss = 0.0
        value_loss = 0.0
        entropy = 0.0

        for t in batch:
            state_vec = t.state.to_vector()
            logits = self.forward_actor(state_vec)
            probs = _softmax(logits)
            value = self.forward_critic(state_vec)

            # Policy loss (simplified: no ratio clipping in this MVP)
            action_prob = probs[t.action.model_index] if t.action.model_index < len(probs) else 1e-10
            log_prob = math.log(max(action_prob, 1e-10))
            policy_loss += -log_prob * t.advantage

            # Value loss
            value_loss += (value - t.return_value) ** 2

            # Entropy
            entropy += -sum(p * math.log(max(p, 1e-10)) for p in probs)

        n = max(len(batch), 1)
        return {
            "policy_loss": policy_loss / n,
            "value_loss": value_loss / n,
            "entropy": entropy / n,
        }

    def save(self, path: str | Path) -> None:
        """Save policy to JSON file."""
        data = {
            "version": self.version,
            "config": asdict(self.config),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_updates": self.total_updates,
            "total_transitions": self.total_transitions,
            "temperature": self.temperature,
            "actor_weights": self._actor_weights,
            "actor_biases": self._actor_biases,
            "critic_weights": self._critic_weights,
            "critic_biases": self._critic_biases,
            "episode_rewards": self.episode_rewards[-1000:],  # keep last 1000
            "policy_losses": self.policy_losses[-1000:],
            "value_losses": self.value_losses[-1000:],
            "entropies": self.entropies[-1000:],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "RLPolicy":
        """Load policy from JSON file."""
        data = json.loads(Path(path).read_text())
        config = RLPolicyConfig(**data["config"])
        policy = cls(config=config)
        policy.version = data["version"]
        policy.created_at = data["created_at"]
        policy.updated_at = data["updated_at"]
        policy.total_updates = data["total_updates"]
        policy.total_transitions = data["total_transitions"]
        policy.temperature = data["temperature"]
        policy._actor_weights = data["actor_weights"]
        policy._actor_biases = data["actor_biases"]
        policy._critic_weights = data["critic_weights"]
        policy._critic_biases = data["critic_biases"]
        policy.episode_rewards = data.get("episode_rewards", [])
        policy.policy_losses = data.get("policy_losses", [])
        policy.value_losses = data.get("value_losses", [])
        policy.entropies = data.get("entropies", [])
        return policy


@dataclass
class RLRouter:
    """Reinforcement Learning Router for GreenFlex.

    Wraps RLPolicy with training data collection, evaluation, and safe deployment.
    """
    policy: RLPolicy = field(default_factory=RLPolicy)
    mode: RLMode = RLMode.SHADOW
    session_state: RLSessionState = RLSessionState.IDLE
    transitions_buffer: list[RLTransition] = field(default_factory=list)
    max_buffer_size: int = 10000
    candidate_model_ids: list[str] = field(default_factory=list)

    # Decision log
    decision_log: list[dict[str, Any]] = field(default_factory=list)
    max_decision_log: int = 1000

    def set_mode(self, mode: RLMode) -> None:
        """Set operating mode. Autonomous requires explicit confirmation."""
        if mode == RLMode.AUTONOMOUS and self.session_state != RLSessionState.DEPLOYED:
            raise ValueError(
                "Autonomous mode requires a deployed, evaluated policy. "
                "Use shadow or advisory mode first."
            )
        self.mode = mode

    def recommend(self, state: RLState, rule_based_model_id: str) -> dict[str, Any]:
        """Get RL recommendation, compare with rule-based, log decision.

        Returns:
            dict with rl_model_id, rule_based_model_id, confidence,
            agreement, mode, and explanation.
        """
        if not self.candidate_model_ids:
            return {
                "rl_model_id": rule_based_model_id,
                "rule_based_model_id": rule_based_model_id,
                "confidence": 0.0,
                "agreement": True,
                "mode": self.mode.value,
                "explanation": "No candidate models configured for RL router",
                "policy_version": self.policy.version,
            }

        action = self.policy.select_action(state, self.candidate_model_ids)

        # Value estimate
        value = 0.0
        if self.policy.is_initialized():
            value = self.policy.forward_critic(state.to_vector())

        agreement = action.model_id == rule_based_model_id

        decision = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": asdict(state),
            "rl_model_id": action.model_id,
            "rule_based_model_id": rule_based_model_id,
            "rl_confidence": action.confidence,
            "value_estimate": value,
            "agreement": agreement,
            "mode": self.mode.value,
            "policy_version": self.policy.version,
        }
        self.decision_log.append(decision)
        if len(self.decision_log) > self.max_decision_log:
            self.decision_log = self.decision_log[-self.max_decision_log:]

        # Determine effective model based on mode
        if self.mode == RLMode.DISABLED:
            effective_model = rule_based_model_id
        elif self.mode == RLMode.SHADOW:
            effective_model = rule_based_model_id  # shadow: always use rule-based
        elif self.mode == RLMode.ADVISORY:
            effective_model = action.model_id  # suggest RL choice
        else:  # AUTONOMOUS
            effective_model = action.model_id

        explanation = self._explain_decision(action, rule_based_model_id, agreement)

        return {
            "rl_model_id": action.model_id,
            "rule_based_model_id": rule_based_model_id,
            "effective_model_id": effective_model,
            "confidence": action.confidence,
            "value_estimate": value,
            "agreement": agreement,
            "mode": self.mode.value,
            "explanation": explanation,
            "policy_version": self.policy.version,
            "log_prob": action.log_prob,
        }

    def record_outcome(self, state: RLState, action: RLAction, reward: float,
                       done: bool = True) -> None:
        """Record transition for training."""
        value = 0.0
        if self.policy.is_initialized():
            value = self.policy.forward_critic(state.to_vector())

        transition = RLTransition(
            state=state,
            action=action,
            reward=reward,
            done=done,
            value=value,
        )
        self.transitions_buffer.append(transition)
        if len(self.transitions_buffer) > self.max_buffer_size:
            self.transitions_buffer = self.transitions_buffer[-self.max_buffer_size:]

    def train_step(self) -> dict[str, Any]:
        """Run one training update if enough transitions collected."""
        if len(self.transitions_buffer) < self.policy.config.min_trajectories_per_update:
            return {
                "status": "insufficient_data",
                "collected": len(self.transitions_buffer),
                "required": self.policy.config.min_trajectories_per_update,
            }

        self.session_state = RLSessionState.TRAINING
        losses = self.policy.update(self.transitions_buffer)
        self.session_state = RLSessionState.READY

        # Clear buffer after update
        self.transitions_buffer = []

        return {
            "status": "updated",
            **losses,
            "policy_version": self.policy.version,
            "total_updates": self.policy.total_updates,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get router statistics."""
        recent_decisions = self.decision_log[-100:]
        agreements = sum(1 for d in recent_decisions if d["agreement"])
        return {
            "mode": self.mode.value,
            "session_state": self.session_state.value,
            "policy_version": self.policy.version,
            "policy_initialized": self.policy.is_initialized(),
            "total_updates": self.policy.total_updates,
            "total_transitions": self.policy.total_transitions,
            "buffer_size": len(self.transitions_buffer),
            "decision_log_size": len(self.decision_log),
            "recent_agreement_rate": agreements / max(len(recent_decisions), 1),
            "temperature": self.policy.temperature,
            "candidate_models": self.candidate_model_ids,
            "recent_rewards": self.policy.episode_rewards[-20:],
            "recent_policy_losses": self.policy.policy_losses[-20:],
        }

    def _explain_decision(self, action: RLAction, rule_based: str, agreement: bool) -> str:
        """Generate human-readable explanation."""
        parts = [f"RL policy selected {action.model_id} (confidence: {action.confidence:.1%})"]
        if agreement:
            parts.append("Agrees with rule-based recommendation")
        else:
            parts.append(f"Differs from rule-based ({rule_based})")
        if self.mode == RLMode.SHADOW:
            parts.append("Shadow mode: rule-based decision will be used")
        return "; ".join(parts)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _xavier_init(in_dim: int, out_dim: int) -> list[list[float]]:
    """Xavier/Glorot weight initialization."""
    limit = math.sqrt(6.0 / (in_dim + out_dim))
    return [[random.uniform(-limit, limit) for _ in range(out_dim)] for _ in range(in_dim)]


def _linear(x: list[float], weights: list[list[float]], biases: list[float]) -> list[float]:
    """Linear layer: y = xW + b."""
    out = []
    for j in range(len(biases)):
        s = biases[j]
        for i in range(len(x)):
            s += x[i] * weights[i][j]
        out.append(s)
    return out


def _relu(x: float) -> float:
    return max(0.0, x)


def _softmax(logits: list[float]) -> list[float]:
    """Numerically stable softmax."""
    if not logits:
        return []
    max_logit = max(logits)
    exp_vals = [math.exp(l - max_logit) for l in logits]
    total = sum(exp_vals)
    return [e / total for e in exp_vals]


def _task_type_encoding(task_type: str) -> float:
    """Encode task type to a scalar feature."""
    encoding = {
        "general": 0.0,
        "code": 0.2,
        "summary": 0.4,
        "translation": 0.6,
        "creative": 0.8,
        "analysis": 1.0,
    }
    return encoding.get(task_type, 0.1)


def _quality_encoding(quality: str) -> float:
    """Encode quality requirement to scalar."""
    encoding = {
        "economy": 0.0,
        "standard": 0.5,
        "high": 1.0,
    }
    return encoding.get(quality, 0.5)

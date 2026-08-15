# ADR 0008: Reinforcement Learning Router (PPO)

## Status

Accepted

## Context

GreenRouter v1/v2 uses a rule-based multi-objective scoring system with fixed
weights. While this is interpretable and auditable, it cannot adapt to:
- User-specific preferences (some users care more about quality, others about cost)
- Task-specific patterns (code generation vs. summarization have different optimal models)
- Changing conditions (grid carbon intensity varies by time and region)
- Model performance drift over time

A reinforcement learning approach can learn optimal routing policies from
historical order data, adapting to user preferences and environmental conditions.

## Decision

Implement a lightweight PPO (Proximal Policy Optimization) router as an
optional layer on top of the rule-based GreenRouter.

### Design Principles

1. **Lightweight**: Pure numpy implementation, no PyTorch/TensorFlow dependency.
   Suitable for local-first deployment.

2. **Safe deployment**: Shadow mode by default. The RL router observes and logs
   decisions but never overrides the rule-based router without explicit user
   consent. Modes: disabled → shadow → advisory → autonomous.

3. **Multi-objective reward**: Same weights as GreenRouter v2:
   - Quality: 35%
   - Price: 20%
   - Energy: 15%
   - Carbon: 10%
   - Latency: 10%
   - Wait time: 5%
   - Renewable share: 5%

4. **Auditable**: Every decision logged with state, action, reward, and policy
   version. Decision history available via API.

5. **Offline-first**: Train on historical order data. Online fine-tuning with
   each completed order.

### State Space

- Task features: input_tokens, output_tokens_est, task_type, quality_requirement,
  deadline_minutes, batch_size
- Context features: carbon_intensity, hour_of_day, day_of_week, gpu_utilization

### Action Space

- Discrete: select one of N candidate models

### Algorithm

- PPO with actor-critic architecture
- Generalized Advantage Estimation (GAE)
- Clipped surrogate objective
- Entropy bonus for exploration
- Temperature decay for exploration-exploitation balance

### Integration

- `RLRouter` wraps `RLPolicy` with training data collection and safe deployment
- In shadow mode, compares RL recommendation with rule-based, logs agreement rate
- Policy can be saved/loaded to JSON for persistence
- Training triggered manually via API (no automatic training in v0.1.0)

## Consequences

### Positive
- Learns user-specific and task-specific routing preferences
- Adapts to changing carbon intensity and energy prices
- Provides a path from rule-based to learned routing
- All decisions auditable and explainable

### Negative
- Requires sufficient training data (minimum 10 trajectories per update)
- PPO implementation is simplified (no full autograd) — adequate for MVP but
  may need upgrade for production
- Shadow mode means no immediate benefit until policy is trained and deployed

### Risks
- Overfitting to small datasets
- Reward hacking (policy exploits reward function loopholes)
- Safety: autonomous mode requires careful evaluation before deployment

## Future Work

- Upgrade to PyTorch for full PPO with proper gradient computation
- Contextual bandit as simpler alternative for cold start
- Offline evaluation before deployment
- Multi-user preference learning
- Transfer learning across GreenFlex deployments

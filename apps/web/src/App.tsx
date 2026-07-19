import { Activity, FileClock, Gauge, Leaf } from 'lucide-react'
import { NavLink, Route, Routes } from 'react-router-dom'

function Placeholder({ title }: { title: string }) {
  return (
    <main className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">用户工作台</p>
          <h1>{title}</h1>
        </div>
        <span className="provenance simulated">仿真信号</span>
      </header>
      <section className="empty-state">
        <Activity aria-hidden="true" />
        <p>工程骨架已就绪，领域功能将在下一锚点接入。</p>
      </section>
    </main>
  )
}

export function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Leaf aria-hidden="true" />
          <span>GreenFlex</span>
        </div>
        <nav aria-label="主导航">
          <NavLink to="/" end><Gauge aria-hidden="true" />工作台</NavLink>
          <NavLink to="/preview"><Activity aria-hidden="true" />单条试跑</NavLink>
          <NavLink to="/orders"><FileClock aria-hidden="true" />推理订单</NavLink>
        </nav>
      </aside>
      <div className="content">
        <Routes>
          <Route path="/" element={<Placeholder title="创建绿色推理订单" />} />
          <Route path="/preview" element={<Placeholder title="单条模型试跑" />} />
          <Route path="/orders" element={<Placeholder title="订单与结果" />} />
          <Route path="*" element={<Placeholder title="页面不存在" />} />
        </Routes>
      </div>
    </div>
  )
}


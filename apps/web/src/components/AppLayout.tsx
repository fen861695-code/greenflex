import {
  Activity,
  ClipboardList,
  FilePlus2,
  Gauge,
  Leaf,
  Menu,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: '工作台', icon: Gauge, end: true },
  { to: '/preview', label: '模型试跑', icon: Activity, end: false },
  { to: '/orders/new', label: '批量下单', icon: FilePlus2, end: false },
  { to: '/orders', label: '订单', icon: ClipboardList, end: true },
]

export function AppLayout() {
  const [open, setOpen] = useState(false)
  return (
    <div className="app-shell">
      <aside className={open ? 'sidebar open' : 'sidebar'}>
        <div className="brand-row">
          <NavLink to="/" className="brand" onClick={() => setOpen(false)}>
            <span className="brand-mark"><Leaf aria-hidden="true" /></span>
            <span><strong>GreenFlex</strong><small>绿色推理订单台</small></span>
          </NavLink>
          <button className="icon-button mobile-only" onClick={() => setOpen(false)} title="关闭菜单">
            <X aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="主导航">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} onClick={() => setOpen(false)}>
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-boundary">
          <span className="status-dot" />
          <span>本地模式</span>
          <small>价格与电力信号为仿真</small>
        </div>
      </aside>
      {open && <button className="scrim" onClick={() => setOpen(false)} aria-label="关闭菜单" />}
      <div className="content">
        <header className="mobile-header mobile-only">
          <button className="icon-button" onClick={() => setOpen(true)} title="打开菜单">
            <Menu aria-hidden="true" />
          </button>
          <span>GreenFlex</span>
          <span className="status-dot" />
        </header>
        <Outlet />
      </div>
    </div>
  )
}

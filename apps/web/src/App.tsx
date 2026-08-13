import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { BatchOrderPage } from './pages/BatchOrderPage'
import { CompliancePage } from './pages/CompliancePage'
import { OrderDetailPage } from './pages/OrderDetailPage'
import { OrdersPage } from './pages/OrdersPage'
import { PassportPage } from './pages/PassportPage'
import { PreviewPage } from './pages/PreviewPage'
import { RLRouterPage } from './pages/RLRouterPage'
import { WorkspacePage } from './pages/WorkspacePage'

export function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WorkspacePage />} />
        <Route path="preview" element={<PreviewPage />} />
        <Route path="orders/new" element={<BatchOrderPage />} />
        <Route path="orders" element={<OrdersPage />} />
        <Route path="orders/:id" element={<OrderDetailPage />} />
        <Route path="passports/:id" element={<PassportPage />} />
        <Route path="rl" element={<RLRouterPage />} />
        <Route path="compliance" element={<CompliancePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

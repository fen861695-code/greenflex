import { Navigate, Route, Routes } from 'react-router-dom'

import { AppLayout } from './components/AppLayout'
import { BatchOrderPage } from './pages/BatchOrderPage'
import { OrderDetailPage } from './pages/OrderDetailPage'
import { OrdersPage } from './pages/OrdersPage'
import { PassportPage } from './pages/PassportPage'
import { PreviewPage } from './pages/PreviewPage'
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
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

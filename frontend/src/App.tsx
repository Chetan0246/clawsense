import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import LiveSensors from './pages/LiveSensors'
import AITrace from './pages/AITrace'
import SafetyCenter from './pages/SafetyCenter'
import SystemHealth from './pages/SystemHealth'
import EventHistory from './pages/EventHistory'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="sensors" element={<LiveSensors />} />
        <Route path="trace" element={<AITrace />} />
        <Route path="safety" element={<SafetyCenter />} />
        <Route path="health" element={<SystemHealth />} />
        <Route path="events" element={<EventHistory />} />
        <Route path="*" element={<Overview />} />
      </Route>
    </Routes>
  )
}

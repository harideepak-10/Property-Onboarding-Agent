import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './styles.css'
import { api, getToken, setToken } from './api'
import Layout from './components/Layout'
import { Loading, ToastProvider, UserCtx } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Properties from './pages/Properties'
import PropertyDetail from './pages/PropertyDetail'
import Procurement from './pages/Procurement'
import MasterList from './pages/MasterList'
import Approvals from './pages/Approvals'
import Licences from './pages/Licences'
import Contacts from './pages/Contacts'
import Purchasing from './pages/Purchasing'
import Schedule from './pages/Schedule'
import Reports from './pages/Reports'
import Users from './pages/Users'

function App() {
  const [user, setUser] = useState(undefined)

  useEffect(() => {
    if (!getToken()) { setUser(null); return }
    api.me().then(setUser).catch(() => setUser(null))
    const out = () => setUser(null)
    window.addEventListener('auth:logout', out)
    return () => window.removeEventListener('auth:logout', out)
  }, [])

  if (user === undefined) return <Loading />
  if (!user) return <Login onLogin={(u) => setUser(u)} />
  const logout = () => { setToken(null); setUser(null) }

  return (
    <UserCtx.Provider value={user}>
    <Routes>
      <Route element={<Layout user={user} onLogout={logout} />}>
        <Route index element={<Dashboard />} />
        <Route path="properties" element={<Properties />} />
        <Route path="properties/:id" element={<PropertyDetail />} />
        <Route path="procurement" element={<Procurement />} />
        <Route path="procurement/:propertyId" element={<Procurement />} />
        <Route path="master-list" element={<MasterList />} />
        <Route path="approvals" element={<Approvals />} />
        <Route path="licences" element={<Licences />} />
        <Route path="contacts" element={<Contacts />} />
        <Route path="buildings" element={<Navigate to="/contacts" replace />} />
        <Route path="purchasing" element={<Purchasing />} />
        <Route path="schedule" element={<Schedule />} />
        <Route path="reports" element={<Reports />} />
        <Route path="users" element={<Users />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
    </UserCtx.Provider>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider><App /></ToastProvider>
    </BrowserRouter>
  </React.StrictMode>
)

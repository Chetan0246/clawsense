import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { LiveDataProvider } from './hooks/useLiveData'
import './index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <LiveDataProvider>
        <App />
      </LiveDataProvider>
    </BrowserRouter>
  </React.StrictMode>,
)

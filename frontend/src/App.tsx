import { useEffect, useState } from 'react'
import {
  ChartLineUp,
  Database,
  GearSix,
  ListChecks,
  Moon,
  Sun,
} from '@phosphor-icons/react'
import { api } from './api'
import { Logo } from './Logo'
import { DataPage } from './views/DataPage'
import { EvalsPage } from './views/EvalsPage'
import { MethodologyPage } from './views/MethodologyPage'
import { SettingsPage } from './views/SettingsPage'

type View = 'evals' | 'methodology' | 'data' | 'settings'

const navItems: Array<{
  id: View
  label: string
  icon: typeof ChartLineUp
}> = [
  { id: 'evals', label: 'Evals', icon: ChartLineUp },
  { id: 'methodology', label: 'Methodology', icon: ListChecks },
  { id: 'data', label: 'Data', icon: Database },
  { id: 'settings', label: 'Settings', icon: GearSix },
]

type ConnectionState = 'checking' | 'online' | 'offline'

export function App() {
  const [activeView, setActiveView] = useState<View>('evals')
  const [dark, setDark] = useState(() => localStorage.getItem('sonar-theme') === 'dark')
  const [connection, setConnection] = useState<ConnectionState>('checking')

  const checkConnection = async () => {
    setConnection('checking')
    try {
      await api.health()
      setConnection('online')
    } catch {
      setConnection('offline')
    }
  }

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('sonar-theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => {
    void checkConnection()
  }, [])

  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="brand-button"
          aria-label="Sonar home"
          onClick={() => setActiveView('evals')}
        >
          <Logo />
          <span>Sonar</span>
        </button>

        <nav className="main-nav" aria-label="Primary navigation">
          {navItems.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${activeView === id ? 'active' : ''}`}
              aria-current={activeView === id ? 'page' : undefined}
              onClick={() => setActiveView(id)}
            >
              <Icon size={14} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="topbar-actions">
          <button
            className="theme-button"
            aria-label={dark ? 'Use light theme' : 'Use dark theme'}
            onClick={() => setDark((current) => !current)}
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>
      </header>

      <div className="workspace-frame">
        <main className="workspace-card">
          {activeView === 'evals' && <EvalsPage dark={dark} />}
          {activeView === 'methodology' && <MethodologyPage />}
          {activeView === 'data' && <DataPage dark={dark} />}
          {activeView === 'settings' && (
            <SettingsPage connection={connection} onRetry={checkConnection} />
          )}
        </main>
      </div>
    </div>
  )
}

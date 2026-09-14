import { NavLink, Route, Routes, useMatch } from 'react-router-dom'

import { MarketPage } from './pages/MarketPage'
import { MarketSetupPage } from './pages/MarketSetupPage'
import { PortfolioPage } from './pages/PortfolioPage'

export function App() {
  const marketMatch = useMatch('/markets/:marketId')
  const setupMatch = useMatch('/markets/new')
  const onMarket = Boolean(marketMatch) && !setupMatch
  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width={22} height={22} />
          <span>MarketScope</span>
        </NavLink>
        <nav className="steps" aria-label="Workflow">
          <NavLink to="/" end>
            <span className="steps__n">1</span> Portfolio
          </NavLink>
          <NavLink to="/markets/new">
            <span className="steps__n">2</span> Market setup
          </NavLink>
          <span className={`steps__item ${onMarket ? 'active' : ''}`} aria-current={onMarket ? 'page' : undefined}>
            <span className="steps__n">3</span> Dashboard
          </span>
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<PortfolioPage />} />
          <Route path="/markets/new" element={<MarketSetupPage />} />
          <Route path="/markets/:marketId" element={<MarketPage />} />
          <Route path="*" element={<div className="page page--narrow">Page not found.</div>} />
        </Routes>
      </main>
    </div>
  )
}

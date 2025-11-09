import { NavLink, Route, Routes } from 'react-router-dom';

import Overview from './pages/Overview';
import Repos from './pages/Repos';
import Actions from './pages/Actions';
import Settings from './pages/Settings';

const App = () => {
  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Sichter</h1>
        <nav className="nav-links">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/repos">Repos</NavLink>
          <NavLink to="/actions">Actions</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/repos" element={<Repos />} />
          <Route path="/actions" element={<Actions />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;

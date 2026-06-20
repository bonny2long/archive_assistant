export default function SuiteNav() {
  return (
    <nav className="suite-nav" aria-label="NAS suite navigation">
      <a href="http://localhost:8091" className="suite-nav__tab">
        <i className="ti ti-inbox" aria-hidden="true" /> Intake Watcher
      </a>
      <a
        href="http://localhost:5173"
        className="suite-nav__tab suite-nav__tab--active"
        aria-current="page"
      >
        <i className="ti ti-archive" aria-hidden="true" /> Archive Assistant
      </a>
      <a href="http://localhost:8092" className="suite-nav__tab">
        <i className="ti ti-sparkles" aria-hidden="true" /> Cleaner
      </a>
    </nav>
  );
}

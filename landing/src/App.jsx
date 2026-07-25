const GITHUB_URL = "https://github.com/NicolasLobosDEV/time_tracker";

const FEATURES = [
  {
    icon: "👥",
    title: "Client & Project Management",
    text: "Organize clients and projects, set hourly rates and monthly time limits, and keep everything in one place.",
  },
  {
    icon: "⏱️",
    title: "Real-time & Manual Tracking",
    text: "Run a live timer for active work or add manual entries for time you tracked away from your desk.",
  },
  {
    icon: "✅",
    title: "Task Management",
    text: "Keep a to-do list with priorities, deadlines, and project links so nothing slips through the cracks.",
  },
  {
    icon: "🧾",
    title: "Expense Tracking",
    text: "Log project expenses, including mileage with automatic cost calculation, right alongside your time.",
  },
  {
    icon: "📄",
    title: "Professional Invoices",
    text: "Turn tracked time and expenses into polished PDF invoices with your own logo and letterhead.",
  },
  {
    icon: "📊",
    title: "Reports & Analytics",
    text: "Visualize tracked time and revenue with clear charts to understand where your hours really go.",
  },
];

const STATS = [
  { num: "5", label: "Platforms supported" },
  { num: "100%", label: "Local & private data" },
  { num: "PDF", label: "One-click invoices" },
  { num: "$0", label: "Monthly fees" },
];

const PLATFORMS = [
  { icon: "🤖", name: "Android" },
  { icon: "🍎", name: "iOS" },
  { icon: "🪟", name: "Windows" },
  { icon: "💻", name: "macOS" },
  { icon: "🐧", name: "Linux" },
];

function Nav() {
  return (
    <header className="nav">
      <div className="container nav__inner">
        <div className="brand">
          <span className="brand__mark">⏱</span>
          <span>Time Tracker</span>
        </div>
        <nav className="nav__links">
          <a href="#features">Features</a>
          <a href="#platforms">Platforms</a>
          <a className="btn btn--primary" href={GITHUB_URL} target="_blank" rel="noreferrer">
            Get Started
          </a>
        </nav>
      </div>
    </header>
  );
}

function Hero() {
  return (
    <section className="hero">
      <div className="container">
        <span className="hero__badge">Free · Open Source · Cross-platform</span>
        <h1>
          Track every <span className="grad">billable minute</span>.
          <br />
          Get paid faster.
        </h1>
        <p>
          A comprehensive time tracking and invoicing app for freelancers,
          consultants, and small teams. Manage clients, log time and expenses,
          and generate professional invoices — all from one place.
        </p>
        <div className="hero__actions">
          <a className="btn btn--primary" href={GITHUB_URL} target="_blank" rel="noreferrer">
            Get Started Free
          </a>
          <a className="btn btn--ghost" href="#features">
            Explore Features
          </a>
        </div>

        <div className="stats">
          {STATS.map((s) => (
            <div className="stat" key={s.label}>
              <div className="stat__num">{s.num}</div>
              <div className="stat__label">{s.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Features() {
  return (
    <section className="section" id="features">
      <div className="container">
        <div className="section__head">
          <h2>Everything you need to bill with confidence</h2>
          <p>
            From the first tracked minute to the final invoice, Time Tracker
            covers the whole workflow.
          </p>
        </div>
        <div className="features">
          {FEATURES.map((f) => (
            <article className="feature" key={f.title}>
              <div className="feature__icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function Platforms() {
  return (
    <section className="section" id="platforms">
      <div className="container">
        <div className="platforms">
          <h2>One codebase. Every device.</h2>
          <p>
            Built with Flutter, Time Tracker runs natively across mobile and
            desktop so your data goes wherever you work.
          </p>
          <div className="platforms__list">
            {PLATFORMS.map((p) => (
              <span className="chip" key={p.name}>
                <span>{p.icon}</span>
                {p.name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="cta">
      <div className="container">
        <h2>Start tracking your time today</h2>
        <p>Free, open source, and yours to run anywhere.</p>
        <a className="btn btn--primary" href={GITHUB_URL} target="_blank" rel="noreferrer">
          View on GitHub
        </a>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__inner">
        <span>© 2026 Time Tracker. Built with Flutter.</span>
        <div>
          <a href={GITHUB_URL} target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <Features />
        <Platforms />
        <CTA />
      </main>
      <Footer />
    </>
  );
}

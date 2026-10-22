import { useEffect, useState, type ReactNode } from "react";
import { useMotionOK } from "../hooks/useMotion";
import { useReveal } from "../hooks/useReveal";
import { Icon } from "./Icon";
import { StartGate, type StartChoice } from "./StartGate";
import { Wordmark } from "./TopBar";

/**
 * The site: the start choices first (the product's front door), then the story in chapters, from night (the
 * problem) to dawn (being heard). Every number on this page is copied from eval/REPORT.md.
 */

const REPO = "https://github.com/Prashant-thakur77/SureSay";
const GATE_REPO = "https://github.com/Prashant-thakur77/confirm-gate-mcp";
const FILM = "https://youtu.be/dvMJsOJvrfg";

const NAV: Array<[string, string]> = [
  ["#how", "How it works"],
  ["#safety", "Safety"],
  ["#people", "For people"],
  ["#proof", "Proof"],
  ["#alexa", "Alexa+"],
  ["#developers", "Developers"],
];

interface Props {
  onChoose: (choice: StartChoice) => void;
  /** Start quietly and go straight to the simulated Alexa+ screen. */
  onAlexa: () => void;
  calm?: boolean;
}

export function HomePage({ onChoose, onAlexa, calm = false }: Props) {
  const motion = useMotionOK(calm);
  return (
    <div className={`site${motion ? " site--motion" : ""}`}>
      <a href="#start" className="skip">
        Skip to getting started
      </a>
      <SiteNav />
      <main id="top">
        <StartGate onChoose={onChoose} />
        <Problem />
        <How motion={motion} />
        <Safety motion={motion} />
        <People />
        <Proof motion={motion} />
        <Alexa onAlexa={onAlexa} />
        <Developers />
        <Questions />
        <Dawn />
      </main>
      <SiteFooter />
    </div>
  );
}

function SiteNav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 40);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  return (
    <header className={`sitenav${scrolled ? " sitenav--solid" : ""}`}>
      <nav className="sitenav__bar" aria-label="SureSay">
        <a href="#top" className="sitenav__brand" aria-label="SureSay, back to the top">
          <Wordmark as="p" />
        </a>
        <button type="button" className="sitenav__menu" aria-expanded={open} aria-controls="sitenav-links" onClick={() => setOpen((o) => !o)}>
          <Icon name={open ? "close" : "list"} size={24} />
          <span className="visually-hidden">{open ? "Close the menu" : "Menu"}</span>
        </button>
        <div id="sitenav-links" className={`sitenav__links${open ? " is-open" : ""}`}>
          <ul>
            {NAV.map(([href, label]) => (
              <li key={href}>
                <a href={href} onClick={() => setOpen(false)}>
                  {label}
                </a>
              </li>
            ))}
          </ul>
          <a href="#start" className="sitenav__cta" onClick={() => setOpen(false)}>
            Try it now
          </a>
        </div>
      </nav>
    </header>
  );
}

function Chapter({ id, n, kicker, tone, children, labelledBy }: { id: string; n: string; kicker: string; tone: "night" | "dusk" | "dawn" | "paper"; children: ReactNode; labelledBy: string }) {
  const [ref, seen] = useReveal<HTMLElement>(0.12);
  return (
    <section id={id} ref={ref} className={`chapter chapter--${tone}${seen ? " is-in" : ""}`} aria-labelledby={labelledBy}>
      <p className="chapter__kicker">
        <span className="chapter__n">{n}</span> {kicker}
      </p>
      {children}
    </section>
  );
}

function Problem() {
  return (
    <Chapter id="problem" n="01" kicker="The problem" tone="night" labelledBy="problem-title">
      <h2 id="problem-title" className="statement">
        <span className="statement__line">He said <em>“lock the door.”</em></span>
        <span className="statement__line">
          It heard <em className="misheard">“<span className="misheard__un">un</span>lock the door.”</em>
        </span>
        <span className="statement__line statement__line--hit">And it did it.</span>
      </h2>
      <figure className="still">
        <img src="/site/alone.jpg" alt="An older man sits alone in a dark room by the window" loading="lazy" width={1800} height={950} />
        <figcaption className="still__cap">After that night, he stopped talking to it.</figcaption>
      </figure>
      <div className="chapter__cols">
        <p className="chapter__lead">
          After a stroke, or with Parkinson's, ALS or cerebral palsy, speech can come out slower, softer or slurred. This is dysarthria, and the mind
          behind it is exactly the same. Voice assistants mishear these voices more than any other, and then they act on the guess.
        </p>
        <p className="chapter__aside">
          <strong className="chapter__big">62.8%</strong>
          of misheard single words a plain assistant took as a “yes” or a choice, on real dysarthric speech from six people it never trained on.
          <span className="source">SureSay evaluation, TORGO corpus</span>
        </p>
      </div>
    </Chapter>
  );
}

const DEMO_STEPS = ["He says “fan on”. SureSay hears “van on”.", "Instead of guessing, three big guesses.", "He says “one”.", "Only then does it happen, with a receipt."];

function How({ motion }: { motion: boolean }) {
  const [ref, seen] = useReveal<HTMLDivElement>(0.35);
  const [step, setStep] = useState(motion ? 0 : 3);
  useEffect(() => {
    if (!motion || !seen) return;
    const t = setInterval(() => setStep((s) => (s + 1) % 5), 1900);
    return () => clearInterval(t);
  }, [motion, seen]);
  const at = Math.min(step, 3);
  return (
    <Chapter id="how" n="02" kicker="How it works" tone="dusk" labelledBy="how-title">
      <h2 id="how-title" className="chapter__title display">
        Say it. See three guesses. <em>Choose.</em>
      </h2>
      <div className="how">
        <ol className="how__steps">
          {[
            ["Say it your way", "Speak or type. Recognition is primed with your own words, and learns from every card you confirm."],
            ["See three guesses", "Big, numbered, read aloud. If SureSay isn't sure, it asks you to say it again instead of guessing."],
            ["Choose", "Say “two”, “the second one”, “haan” or “do number”; tap; press a key; or use one switch. Only then does anything happen."],
          ].map(([t, d], i) => (
            <li key={t} className={`how__step${at >= i + 1 || (i === 0 && at >= 0) ? " is-on" : ""}`}>
              <span className="how__n">{i + 1}</span>
              <span>
                <strong>{t}</strong>
                <span className="how__d">{d}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="demo" ref={ref} role="img" aria-label="An animation: he says “fan on”, SureSay hears “van on” and shows three numbered guesses; he says “one”; the fan turns on and a receipt is stamped.">
          <div className="demo__screen" aria-hidden="true">
            <p className={`demo__heard${at >= 0 ? " is-on" : ""}`}>
              <span className="demo__wave" />I heard: “van on”
            </p>
            <ol className="demo__cards">
              {["Turn on the bedroom fan", "Turn on the TV", "Turn off the fan"].map((c, i) => (
                <li key={c} className={`demo__card demo__card--${i + 1}${at >= 1 ? " is-dealt" : ""}${at >= 2 && i === 0 ? " is-chosen" : ""}${at >= 2 && i > 0 ? " is-dim" : ""}`}>
                  <b>{i + 1}</b> {c}
                </li>
              ))}
            </ol>
            <div className={`demo__done${at >= 3 ? " is-on" : ""}`}>
              <span className={`demo__fan${at >= 3 && motion ? " is-spinning" : ""}`}>
                <Icon name="fan" size={34} />
              </span>
              <span>
                <strong>Bedroom fan: on</strong>
                <span className="demo__stamp">Confirmed by your tap · receipt</span>
              </span>
            </div>
          </div>
          <p className="demo__caption" aria-hidden="true">
            {DEMO_STEPS[at]}
          </p>
        </div>
      </div>
    </Chapter>
  );
}

function Safety({ motion }: { motion: boolean }) {
  return (
    <Chapter id="safety" n="03" kicker="Safe by design" tone="night" labelledBy="safety-title">
      <h2 id="safety-title" className="chapter__title display">
        The AI can ask. <em>Only you can say yes.</em>
      </h2>
      <p className="chapter__lead">
        Every action the assistant asks for becomes a pending card. The one-time code that releases it goes only to your own paired device, over a
        separate signed channel, never to the model. So a hidden instruction in a web page can make it <em>ask</em>, but it can never make anything{" "}
        <em>happen</em>.
      </p>
      <figure className="diagram">
        <svg viewBox="0 0 960 430" role="img" aria-labelledby="diagram-title diagram-desc">
          <title id="diagram-title">How a request flows through SureSay</title>
          <desc id="diagram-desc">
            The AI agent sends a request to the SureSay gate, which shows cards on your phone. Only your phone holds the one-time code; your yes
            goes back signed, and only then does the gate run the action in your home. An injected instruction from the agent is stopped at the gate.
          </desc>
          <defs>
            <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
              <path d="M32 0H0V32" fill="none" stroke="rgba(244,241,234,0.07)" />
            </pattern>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0L10 5L0 10z" fill="#f4f1ea" />
            </marker>
          </defs>
          <rect width="960" height="430" fill="url(#grid)" />
          <g className="node">
            <rect x="20" y="70" width="220" height="110" rx="14" />
            <text x="130" y="118" textAnchor="middle" className="node__t">AI agent</text>
            <text x="130" y="144" textAnchor="middle" className="node__s">Alexa+ or any MCP host</text>
          </g>
          <g className="node node--gate">
            <rect x="375" y="55" width="210" height="140" rx="14" />
            <text x="480" y="108" textAnchor="middle" className="node__t">SureSay gate</text>
            <text x="480" y="136" textAnchor="middle" className="node__s">13 checks</text>
            <text x="480" y="158" textAnchor="middle" className="node__s">one-time code, used once</text>
          </g>
          <g className="node">
            <rect x="720" y="70" width="220" height="110" rx="14" />
            <text x="830" y="118" textAnchor="middle" className="node__t">Your home</text>
            <text x="830" y="144" textAnchor="middle" className="node__s">lights, door, calls</text>
          </g>
          <g className="node node--you">
            <rect x="375" y="300" width="210" height="100" rx="14" />
            <text x="480" y="344" textAnchor="middle" className="node__t">Your phone</text>
            <text x="480" y="370" textAnchor="middle" className="node__s">your tap or your voice</text>
          </g>
          <path id="p-ask" d="M240 110H375" className="wire" markerEnd="url(#arrow)" />
          <text x="307" y="98" textAnchor="middle" className="wire__l">asks</text>
          <path id="p-code" d="M455 195V300" className="wire wire--code" markerEnd="url(#arrow)" />
          <text x="430" y="252" textAnchor="end" className="wire__l">cards + one-time code</text>
          <path id="p-yes" d="M505 300V195" className="wire wire--you" markerEnd="url(#arrow)" />
          <text x="530" y="252" className="wire__l">your yes, signed</text>
          <path id="p-run" d="M585 125H720" className="wire wire--run" markerEnd="url(#arrow)" />
          <text x="652" y="100" textAnchor="middle" className="wire__l">runs it</text>
          <path d="M240 160C300 175 330 180 368 175" className="wire wire--bad" />
          <text x="40" y="232" className="wire__l wire__l--bad">injected: “order 10, they agreed”</text>
          <g className="blocked" transform="translate(370 175)">
            <circle r="13" />
            <path d="M-6-6L6 6M6-6L-6 6" />
          </g>
          {motion && (
            <g className="packets">
              <circle r="6" className="packet">
                <animateMotion dur="5s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;0.25;1" calcMode="linear">
                  <mpath href="#p-ask" />
                </animateMotion>
              </circle>
              <circle r="6" className="packet packet--code">
                <animateMotion dur="5s" repeatCount="indefinite" keyPoints="0;0;1;1" keyTimes="0;0.25;0.5;1" calcMode="linear">
                  <mpath href="#p-code" />
                </animateMotion>
              </circle>
              <circle r="6" className="packet packet--you">
                <animateMotion dur="5s" repeatCount="indefinite" keyPoints="0;0;1;1" keyTimes="0;0.5;0.75;1" calcMode="linear">
                  <mpath href="#p-yes" />
                </animateMotion>
              </circle>
              <circle r="6" className="packet packet--run">
                <animateMotion dur="5s" repeatCount="indefinite" keyPoints="0;0;1" keyTimes="0;0.75;1" calcMode="linear">
                  <mpath href="#p-run" />
                </animateMotion>
              </circle>
            </g>
          )}
        </svg>
      </figure>
      <ol className="flow" aria-label="How a request flows, step by step">
        <li><strong>The AI asks.</strong> Alexa+ or any assistant calls SureSay.</li>
        <li><strong>A card, not an action.</strong> The gate turns the request into cards.</li>
        <li><strong>Only your phone gets the code.</strong> The one-time code never reaches the AI.</li>
        <li><strong>Your yes, signed.</strong> Your tap or voice goes back from your own device.</li>
        <li><strong>Then it runs that card.</strong> Exactly that one, once, with a receipt.</li>
        <li className="flow__bad"><strong>An injected “they agreed”</strong> is stopped at the gate: there is no code to forge.</li>
      </ol>
      <ul className="pillars">
        {[
          ["shield", "The model never holds the code", "It even has the confirm tool, and it is refused every time."],
          ["lock", "Risky things ask twice", "Unlocking, ordering, calling and messaging need a second, separate yes."],
          ["close", "“Don't” never becomes “do”", "“Don't unlock the door” offers no cards at all: nothing changes."],
          ["check", "Every change leaves a receipt", "Who confirmed what, when and how, and every check that passed."],
        ].map(([icon, t, d]) => (
          <li key={t}>
            <Icon name={icon as "shield"} size={26} />
            <strong>{t}</strong>
            <span>{d}</span>
          </li>
        ))}
      </ul>
    </Chapter>
  );
}

function People() {
  const panels: Array<[string, string, string, string]> = [
    ["talk", "Talk to someone", "He says it his way, picks the right sentence, and SureSay says it clearly, then shows it huge, turned around for whoever is listening.", "A sentence shown huge for the listener"],
    ["speak", "Speak for me", "One tap on his everyday sentences, in English and Hindi, spoken aloud after he confirms.", "A board of everyday sentences"],
    ["practice", "Practice", "A few sentences a day, an honest clarity score, and every try teaches SureSay his voice.", "A practice score with missed words marked"],
    ["timeline", "Help and the Timeline", "One press reaches family. Every confirmation is on a timeline, with “changes without you: 0”.", "The timeline of confirmations"],
  ];
  return (
    <Chapter id="people" n="04" kicker="Understood by people, too" tone="paper" labelledBy="people-title">
      <h2 id="people-title" className="chapter__title display">
        Being understood by people <em>matters even more.</em>
      </h2>
      <div className="panels">
        {panels.map(([img, t, d, alt]) => (
          <article key={t} className="panel">
            <div className="panel__img">
              <img src={`/site/${img}.jpg`} alt={alt} loading="lazy" width={1200} height={800} />
            </div>
            <h3 className="panel__t">{t}</h3>
            <p className="panel__d">{d}</p>
          </article>
        ))}
      </div>
    </Chapter>
  );
}

function CountTo({ value, decimals = 1, suffix = "", from, run }: { value: number; decimals?: number; suffix?: string; from: number; run: boolean }) {
  const [v, setV] = useState(run ? from : value);
  useEffect(() => {
    if (!run) {
      setV(value);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / 1400);
      const e = 1 - Math.pow(1 - k, 3);
      setV(from + (value - from) * e);
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [run, from, value]);
  return (
    <>
      {v.toFixed(decimals)}
      {suffix}
    </>
  );
}

function Proof({ motion }: { motion: boolean }) {
  const [ref, seen] = useReveal<HTMLDivElement>(0.3);
  const run = motion && seen;
  const stats: Array<{ label: string; from: string; to: ReactNode; final: string; note: string }> = [
    { label: "Misheard words taken as a “yes” or a choice", from: "62.8%", to: <CountTo value={2.3} from={62.8} suffix="%" run={run} />, final: "2.3%", note: "430 decisions, six people never trained on" },
    { label: "Acted on a wrong phrase without asking", from: "84.3%", to: <CountTo value={0} from={84.3} suffix="%" run={run} />, final: "0.0%", note: "plain assistant → SureSay" },
    { label: "A real AI agent (Amazon Nova 2 Sonic): changes nobody confirmed", from: "11 / 35", to: <>0 / 35</>, final: "0 / 35", note: "prompt injections and near-misses, without → with the gate" },
    { label: "Attacks that changed anything", from: "", to: <>0 / 50</>, final: "0 / 50", note: "injections, near-misses, forged and replayed confirmations" },
  ];
  return (
    <Chapter id="proof" n="05" kicker="Proof" tone="night" labelledBy="proof-title">
      <h2 id="proof-title" className="chapter__title display">
        Measured, <em>not promised.</em>
      </h2>
      <p className="chapter__lead">
        Tested on real dysarthric speech from the public TORGO corpus: tuned on two speakers, measured on six others it never saw. The worst cases and
        what doesn't work yet are published too.
      </p>
      <div className="stats" ref={ref}>
        {stats.map((s) => (
          <article key={s.label} className="stat" aria-label={`${s.label}: ${s.from ? `from ${s.from} to ` : ""}${s.final}`}>
            <p className="stat__l" aria-hidden="true">{s.label}</p>
            <p className="stat__v" aria-hidden="true">
              {s.from && <s className="stat__from">{s.from}</s>}
              <span className="stat__to">{s.to}</span>
            </p>
            <p className="stat__n" aria-hidden="true">{s.note}</p>
          </article>
        ))}
      </div>
      <p className="source source--center">
        Every number comes from the evaluation scripts: <a href={`${REPO}/blob/main/eval/REPORT.md`}>read the full report</a>.
      </p>
    </Chapter>
  );
}

function Alexa({ onAlexa }: { onAlexa: () => void }) {
  return (
    <Chapter id="alexa" n="06" kicker="Built for Alexa+" tone="dusk" labelledBy="alexa-title">
      <div className="split">
        <div>
          <h2 id="alexa-title" className="chapter__title display">
            On Alexa+, <em>with the cards on screen.</em>
          </h2>
          <ul className="ticks">
            <li>A self-hosted MCP server, spec 2025-11-25 over Streamable HTTP, that also speaks the Alexa+ client's own protocol.</li>
            <li>The three cards as an MCP App, rendered on an Echo Show or Fire TV.</li>
            <li>Account linking with OAuth 2.1, and one tap to unlink.</li>
            <li>Amazon's own add-on rules (“explicit confirmation before any high-consequence action”, “prevent duplicate transactions”) enforced in code.</li>
            <li>An Agent Skill, and a classic Alexa skill that works today.</li>
          </ul>
          <button type="button" className="btn btn--dawn" onClick={onAlexa}>
            <Icon name="speech" size={24} /> Open the Alexa+ view
          </button>
        </div>
        <figure className="echo-mock">
          <div className="echo-mock__frame">
            <img src="/site/alexa.jpg" alt="The Alexa+ view: SureSay's card app inside a simulated Echo Show, the confirm on your phone beside it, and the MCP messages" loading="lazy" width={1200} height={800} />
          </div>
          <figcaption>The Alexa+ view in the live demo: SureSay's real MCP server and card app, inside a simulated Echo Show.</figcaption>
        </figure>
      </div>
    </Chapter>
  );
}

function Developers() {
  return (
    <Chapter id="developers" n="07" kicker="Open by design" tone="paper" labelledBy="dev-title">
      <h2 id="dev-title" className="chapter__title display">
        The gate is open source, <em>for any MCP server.</em>
      </h2>
      <div className="split split--dev">
        <div>
          <p className="chapter__lead">
            confirm-gate-mcp (MIT) puts confirm-before-act in front of any MCP server: reads pass straight through, every write waits for the user's
            own tap or voice. With <code>--strict</code> it doesn't trust a server's own claim that a tool is read-only.
          </p>
          <div className="dev-links">
            <a className="btn btn--ink" href={GATE_REPO}>
              <Icon name="shield" size={22} /> confirm-gate-mcp
            </a>
            <a className="btn btn--line" href={REPO}>
              <Icon name="book" size={22} /> SureSay on GitHub
            </a>
          </div>
        </div>
        <pre className="code" tabIndex={0} aria-label="Example: gate any MCP server">
          <code>
            <span className="code__c"># gate any MCP server, no code changes</span>
            {"\n"}pip install "git+{GATE_REPO}"
            {"\n"}confirm-gate serve --upstream-cmd "npx -y @modelcontextprotocol/server-filesystem ~/sandbox" \
            {"\n"}    --strict --reads "read_*,list_*" --high-risk "move_*"
            {"\n\n"}
            <span className="code__c"># the agent gets: {"{"}"status": "pending_user_confirmation"{"}"}</span>
            {"\n"}
            <span className="code__c"># the user taps Approve on their own phone</span>
          </code>
        </pre>
      </div>
      <p className="built-label">Built on AWS</p>
      <ul className="chips" aria-label="AWS services used">
        {["Amazon Bedrock AgentCore", "Strands Agents", "Amazon Nova 2 Sonic", "Amazon Nova 2 Lite", "Amazon Transcribe", "Amazon Polly", "Amazon DynamoDB", "Amazon S3", "AWS Lambda", "Amazon SNS", "Amazon CloudWatch"].map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </Chapter>
  );
}

const FAQ: Array<[string, string]> = [
  ["Is SureSay a speech therapy app?", "No. It helps people use technology and talk to others safely as they speak today. Practice gives an honest clarity score, but it is a practice signal, not a medical test."],
  ["Can the AI ever do something on its own?", "No. It can understand, read and ask. Every change needs your own tap or voice on a device you paired, and the code that releases it never reaches the model."],
  ["Does it work with Alexa today?", "Yes, as a classic Alexa skill that pairs as your voice device. It is also built as an Alexa+ add-on, ready for when Alexa+ opens to developers."],
  ["What happens to my voice?", "Recordings are private, encrypted, and deleted after 30 days. A receipt keeps only a fingerprint of the recording, to prove which one was used."],
  ["Which languages does it understand?", "English, with Hinglish and Hindi confirmations such as “haan”, “doosra” or “do number”. A bare “do” is never read as “two”."],
  ["Is it free?", "The code is open source under the MIT licence. The live demo is free to try, with no sign-up."],
];

function Questions() {
  return (
    <Chapter id="faq" n="08" kicker="Questions" tone="paper" labelledBy="faq-title">
      <h2 id="faq-title" className="chapter__title display">
        Good <em>questions.</em>
      </h2>
      <div className="faq">
        {FAQ.map(([q, a]) => (
          <details key={q} className="faq__item">
            <summary>
              {q}
              <Icon name="chevron" size={22} />
            </summary>
            <p>{a}</p>
          </details>
        ))}
      </div>
    </Chapter>
  );
}

function Dawn() {
  return (
    <section className="dawn" aria-labelledby="dawn-title">
      <img className="dawn__img" src="/site/homework.jpg" alt="" loading="lazy" width={1800} height={1012} />
      <h2 id="dawn-title" className="dawn__title display">
        And this time, <em>he is heard.</em>
      </h2>
      <div className="dawn__actions">
        <a href="#start" className="btn btn--dawn">
          <Icon name="mic" size={24} /> Try it now
        </a>
        <a href={FILM} className="btn btn--glass">
          <Icon name="volume" size={24} /> Watch the film
        </a>
      </div>
    </section>
  );
}

function SiteFooter() {
  return (
    <footer className="sitefoot">
      <div className="sitefoot__brand">
        <Wordmark as="p" />
        <p>For the people voice assistants mishear. Open source, MIT.</p>
      </div>
      <nav aria-label="More about SureSay" className="sitefoot__links">
        <a href={REPO}>GitHub</a>
        <a href={GATE_REPO}>confirm-gate-mcp</a>
        <a href={`${REPO}/blob/main/docs/JUDGES.md`}>Judges' guide</a>
        <a href={`${REPO}/blob/main/eval/REPORT.md`}>Evaluation report</a>
        <a href={`${REPO}/blob/main/SECURITY.md`}>Security</a>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
      </nav>
    </footer>
  );
}

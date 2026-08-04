import { useEffect, useRef, type CSSProperties } from "react";

import CitationTag from "../components/CitationTag";
import FoilButton from "../components/FoilButton";
import HoldTile from "../components/HoldTile";
import ReasonTag from "../components/ReasonTag";
import WallChart from "../components/WallChart";
import {
  BADGE,
  CITATIONS_SECTION,
  FINAL_CTA,
  FOOTER,
  HERO,
  LETTER,
  METHOD_SECTION,
  MOCKUP,
  NAV_LINKS,
  PETITIONS_SECTION,
  PROOF,
  SAVINGS_SECTION,
  STAKES_SECTION,
  STAKES_WALL_STEPS,
} from "../lib/landing";

import "./Landing.css";

// The marketing landing page, layout per the design export
// (docs/design/triage-board/Foothold Landing.dc.html); copy per
// lib/landing.ts. Every "Check my credits" placement enters the app at the
// route picker. Rendering is deterministic: the hero gradient and wall
// sheens are fixed CSS keyframes, the foil sheen is pointer-driven, and the
// scroll reveal is a pure function of viewport intersection - the export's
// PRNG chance-event loop stays on the triage sidebar only, never here.
export default function Landing({ onEnter }: { onEnter: () => void }) {
  const rootRef = useRef<HTMLDivElement>(null);

  // The export's [data-fade] reveal: elements stay visible by default and
  // are hidden for the fade-in only once the observer is confirmed live, so
  // an environment without IntersectionObserver callbacks degrades to a
  // fully visible page after the fallback timeout.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) {
      return;
    }
    const els = Array.from(root.querySelectorAll<HTMLElement>("[data-fade]"));
    const revealed = new WeakSet<HTMLElement>();
    const reveal = (el: HTMLElement) => {
      revealed.add(el);
      el.style.opacity = "1";
      el.style.transform = "none";
    };
    let ioWorks = false;
    const io = new IntersectionObserver(
      (entries) => {
        if (!ioWorks) {
          ioWorks = true;
          els.forEach((el) => {
            if (!revealed.has(el)) {
              el.style.opacity = "0";
              el.style.transform = "translateY(24px)";
            }
          });
        }
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            reveal(entry.target as HTMLElement);
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 },
    );
    els.forEach((el) => {
      el.style.transition = "opacity .7s ease, transform .7s ease";
      io.observe(el);
    });
    const fallback = window.setTimeout(() => {
      if (!ioWorks) {
        io.disconnect();
        els.forEach(reveal);
      }
    }, 600);
    return () => {
      io.disconnect();
      clearTimeout(fallback);
      els.forEach((el) => {
        el.style.opacity = "";
        el.style.transform = "";
        el.style.transition = "";
      });
    };
  }, []);

  return (
    <div className="landing" ref={rootRef}>
      <div className="landing__hero">
        <div className="landing__flow" />
        <div className="landing__flow landing__flow--accent" />
        <div className="landing__veil" />
        <div className="landing__herobody">
          <div className="landing__nav">
            <div className="landing__brand">
              <svg width="26" height="22" viewBox="0 0 26 22">
                <rect x="0" y="14" width="7" height="8" fill="#FFFFFF" />
                <rect x="9" y="8" width="7" height="14" fill="#FFFFFF" />
                <rect x="18" y="1" width="7" height="21" fill="none" stroke="#FFFFFF" strokeWidth="2" />
              </svg>
              <span>FOOTHOLD</span>
            </div>
            <div className="landing__navlinks">
              {NAV_LINKS.map((link) => (
                <a key={link.href} className="landing__navlink" href={link.href}>
                  {link.label}
                </a>
              ))}
              <button className="landing__navcta" onClick={onEnter}>
                {HERO.navCta}
              </button>
            </div>
          </div>
          <div className="landing__herocopy">
            <div className="landing__badge">{BADGE}</div>
            <h1 className="landing__headline">{HERO.headline}</h1>
            <p className="landing__tagline">{HERO.tagline}</p>
            <div className="landing__ctas">
              <FoilButton size="md" shape="pill" onClick={onEnter}>
                {HERO.cta}
              </FoilButton>
              <a className="landing__ghost" href="#method">
                {HERO.secondaryCta}
              </a>
            </div>
          </div>
        </div>
      </div>

      <div className="landing__mockwrap" data-fade>
        <div className="landing__mock">
          <div className="landing__mockbar">
            <svg width="18" height="15" viewBox="0 0 26 22">
              <rect x="0" y="14" width="7" height="8" fill="#F3F1EC" />
              <rect x="9" y="8" width="7" height="14" fill="#F3F1EC" />
              <rect x="18" y="1" width="7" height="21" fill="#0E8A6D" stroke="#F3F1EC" strokeWidth="2" />
            </svg>
            <span className="landing__mockroute">{MOCKUP.routeLine}</span>
            <div className="landing__mocktabs">
              <span className="landing__mocktab landing__mocktab--active">{MOCKUP.tabs[0]}</span>
              <span className="landing__mocktab">{MOCKUP.tabs[1]}</span>
            </div>
          </div>
          <div className="landing__mockboard">
            {MOCKUP.rows.map((row, i) => (
              <div
                key={row.bucket}
                className="landing__mockrow"
                style={{ "--fh-stagger": `${28 * i}px` } as CSSProperties}
              >
                <div className="landing__mockhead">
                  <HoldTile bucket={row.bucket} size={20} frame="slate" shadow />
                  <span className="landing__mocklabel">{row.label}</span>
                  <span className="landing__mockcount">{row.countLine}</span>
                </div>
                {row.bucket === "at_risk" ? (
                  <div className="landing__mockgrid">
                    {row.cards.map((card) => (
                      <div key={card.code} className="landing__mockcell">
                        <div className="landing__mockcourse">
                          <span className="landing__code">{card.code}</span> {card.title}{" "}
                          <span className="landing__code">{card.target}</span>
                        </div>
                        <div className="landing__mockmeta">
                          {card.reasonCode && <ReasonTag code={card.reasonCode} />}
                          <span className="landing__mocknote">{card.reasonNote}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  row.cards.map((card) => (
                    <div key={card.code} className="landing__mockcard">
                      <div className="landing__mockmain">
                        <div className="landing__mockcourse">
                          <span className="landing__code">{card.code}</span> {card.title}{" "}
                          {card.target && <span className="landing__code">{card.target}</span>}
                          {card.targetTitle && <> {card.targetTitle}</>}
                          {card.fallback && (
                            <span className="landing__mockfallback citation citation--no_articulation">
                              {card.fallback}
                            </span>
                          )}
                        </div>
                        {card.citation && (
                          <div className="landing__mockcite">
                            <CitationTag
                              citation={card.citation}
                              majorKey="demo"
                              bucket={row.bucket}
                              small
                            />
                          </div>
                        )}
                      </div>
                      <span className="landing__mockunits">{card.units}</span>
                    </div>
                  ))
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="landing__proof" data-fade>
        <div className="landing__prooflabel">{PROOF.label}</div>
        <div className="landing__colleges">
          {PROOF.colleges.map((name) => (
            <span key={name}>{name}</span>
          ))}
        </div>
      </div>

      <section id="citations" className="landing__feature">
        <div data-fade>
          <div className="landing__kicker">{CITATIONS_SECTION.kicker}</div>
          <h2 className="landing__h2">{CITATIONS_SECTION.headline}</h2>
          <p className="landing__body">{CITATIONS_SECTION.body}</p>
          <a
            className="landing__link"
            onClick={onEnter}
            onKeyDown={(e) => e.key === "Enter" && onEnter()}
            role="button"
            tabIndex={0}
          >
            {CITATIONS_SECTION.link}
          </a>
        </div>
        <div className="landing__panel" data-fade>
          <div className="landing__mockcard landing__mockcard--loose">
            <div className="landing__mockmain">
              <div className="landing__panelcourse">
                <span className="landing__code">{CITATIONS_SECTION.card.code}</span>{" "}
                {CITATIONS_SECTION.card.title}{" "}
                <span className="landing__code">{CITATIONS_SECTION.card.target}</span>
              </div>
              <div className="landing__mockmeta">
                <ReasonTag code={CITATIONS_SECTION.card.reasonCode} />
                <span className="landing__panelnote">{CITATIONS_SECTION.card.reasonNote}</span>
              </div>
              <div className="landing__panelcite citation citation--at_risk">
                {CITATIONS_SECTION.card.citation}
              </div>
            </div>
          </div>
          <div className="landing__arrow">↓</div>
          <div className="landing__receipt">
            <div className="landing__receipthead">{CITATIONS_SECTION.receipt.header}</div>
            <div className="landing__receiptline">
              {CITATIONS_SECTION.receipt.lead}
              <span className="landing__receiptquote">{CITATIONS_SECTION.receipt.quote}</span>
            </div>
            <div className="landing__receiptverified">{CITATIONS_SECTION.receipt.verified}</div>
          </div>
        </div>
      </section>

      <div id="method" className="landing__band">
        <div className="landing__feature landing__feature--inband">
          <div className="landing__panel landing__panel--card" data-fade>
            <div className="landing__checks">
              {METHOD_SECTION.steps.map((step) => (
                <div key={step.label} className="landing__check">
                  <HoldTile bucket={step.flag ? "at_risk" : "transfers_clean"} size={20} frame="slate" />
                  <span>{step.label}</span>
                </div>
              ))}
            </div>
            <div className="landing__checksfoot">{METHOD_SECTION.cardFoot}</div>
          </div>
          <div data-fade>
            <div className="landing__kicker">{METHOD_SECTION.kicker}</div>
            <h2 className="landing__h2">{METHOD_SECTION.headline}</h2>
            <p className="landing__body">{METHOD_SECTION.body}</p>
          </div>
        </div>
      </div>

      <section id="petitions" className="landing__feature">
        <div data-fade>
          <div className="landing__kicker">{PETITIONS_SECTION.kicker}</div>
          <h2 className="landing__h2">{PETITIONS_SECTION.headline}</h2>
          <p className="landing__body">{PETITIONS_SECTION.body}</p>
          <a
            className="landing__link"
            onClick={onEnter}
            onKeyDown={(e) => e.key === "Enter" && onEnter()}
            role="button"
            tabIndex={0}
          >
            {PETITIONS_SECTION.link}
          </a>
        </div>
        <div className="landing__panel" data-fade>
          <div className="landing__flags">
            {PETITIONS_SECTION.flags.map((flag) => (
              <div key={flag.code} className="landing__flag">
                <span className="landing__flagcheck">
                  <svg width="9" height="9" viewBox="0 0 20 20">
                    <path d="M4 10.5l4 4 8-9" stroke="#F3F1EC" strokeWidth="4" fill="none" />
                  </svg>
                </span>
                <span className="landing__flagcode">{flag.code}</span>
                <span className="landing__flagtitle">{flag.title}</span>
                <ReasonTag code={flag.reasonCode} />
              </div>
            ))}
          </div>
          <div className="landing__receipt landing__receipt--letter">
            <div className="landing__receipthead">{PETITIONS_SECTION.draftHeader}</div>
            <p className="landing__letter">
              {LETTER.salutation}
              <br />
              {LETTER.body[0]}
              <span className="landing__code">{LETTER.body[1]}</span>
              {LETTER.body[2]}
              <span className="landing__code">{LETTER.body[3]}</span>
              {LETTER.body[4]}
              <span className="landing__lettercite">{LETTER.body[5]}</span>
              {LETTER.body[6]}
            </p>
            <div className="landing__copychip">{PETITIONS_SECTION.copyButton}</div>
          </div>
        </div>
      </section>

      <div className="landing__stakes">
        <div className="landing__stakesgrid">
          <div data-fade>
            <div className="landing__kicker landing__kicker--dark">{STAKES_SECTION.kicker}</div>
            <div className="landing__stat">{STAKES_SECTION.stat}</div>
            <h2 className="landing__h2 landing__h2--stat">{STAKES_SECTION.headline}</h2>
            <p className="landing__body landing__body--dark">{STAKES_SECTION.body}</p>
          </div>
          <div data-fade>
            <div className="landing__walltitle">{STAKES_SECTION.wallTitle}</div>
            <WallChart steps={STAKES_WALL_STEPS} variant="landing" />
            <div className="landing__wallcaption">
              {STAKES_SECTION.captionTop}
              <br />
              {STAKES_SECTION.captionBottom}
            </div>
          </div>
        </div>
      </div>

      <section id="savings" className="landing__feature">
        <div className="landing__panel landing__panel--stack" data-fade>
          {SAVINGS_SECTION.cards.map((card) => (
            <div key={card.rank} className="landing__mockcard landing__mockcard--rank">
              <span className="landing__rank">{card.rank}</span>
              <div className="landing__mockmain">
                <div className="landing__mockcourse">
                  <span className="landing__code">{card.code}</span> {card.title}{" "}
                  <span className="landing__code">{card.target}</span> {card.targetTitle}
                </div>
                <div className="landing__mockcite">
                  <CitationTag citation={card.citation} majorKey="demo" bucket="transfers_clean" small />
                </div>
              </div>
              <div className="landing__save">
                <div className="landing__saveamount">{card.savings}</div>
                <div className="landing__savelabel">{SAVINGS_SECTION.saveLabel}</div>
              </div>
            </div>
          ))}
        </div>
        <div data-fade>
          <div className="landing__kicker">{SAVINGS_SECTION.kicker}</div>
          <h2 className="landing__h2">{SAVINGS_SECTION.headline}</h2>
          <p className="landing__body">{SAVINGS_SECTION.body}</p>
        </div>
      </section>

      <div className="landing__final">
        <div className="landing__finalcopy" data-fade>
          <h2 className="landing__h2 landing__h2--final">{FINAL_CTA.headline}</h2>
          <p className="landing__body landing__body--final">{FINAL_CTA.body}</p>
          <div className="landing__finalcta">
            <FoilButton size="lg" shape="pill" onClick={onEnter}>
              {FINAL_CTA.cta}
            </FoilButton>
          </div>
          <div className="landing__fineprint">{FINAL_CTA.finePrint}</div>
        </div>
        <div className="landing__footer">
          <div className="landing__footerrow">
            <div className="landing__brand landing__brand--footer">
              <svg width="20" height="17" viewBox="0 0 26 22">
                <rect x="0" y="14" width="7" height="8" fill="#272B31" />
                <rect x="9" y="8" width="7" height="14" fill="#272B31" />
                <rect x="18" y="1" width="7" height="21" fill="#0E8A6D" stroke="#272B31" strokeWidth="2" />
              </svg>
              <span>FOOTHOLD</span>
            </div>
            <span className="landing__footertag">{FOOTER.tagline}</span>
            <div className="landing__footerlinks">
              {FOOTER.links.map((link) => (
                <a key={link.href} href={link.href}>
                  {link.label}
                </a>
              ))}
            </div>
            <span className="landing__provenance">{FOOTER.provenance}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

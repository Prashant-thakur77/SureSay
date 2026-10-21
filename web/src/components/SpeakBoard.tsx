import type { CSSProperties } from "react";
import { boardTiles } from "../lib/phrases";
import type { Phrase } from "../lib/types";
import { Icon } from "./Icon";
import { useScanMark } from "./scan";

/**
 * Big tiles of things to say out loud. A tap only opens a card ("Say out
 * loud: …?"), which the user confirms like anything else; then SureSay
 * speaks it for the people nearby.
 */
export function SpeakBoard({ phrasebook, onSay, busy }: { phrasebook: Phrase[]; onSay: (text: string) => void; busy: boolean }) {
  const tiles = boardTiles(phrasebook);
  return (
    <section className="board" aria-labelledby="board-title">
      <h2 id="board-title" className="stage__title display">
        Speak <em>for me</em>
      </h2>
      <p className="stage__lead">Tap what you want to say. You confirm it, then I say it out loud.</p>
      <ul className="board__grid">
        {tiles.map((t, i) => (
          <li key={t.key} style={{ "--i": i } as CSSProperties}>
            <BoardTile tile={t} index={i} onSay={onSay} busy={busy} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function BoardTile({ tile, index, onSay, busy }: { tile: ReturnType<typeof boardTiles>[number]; index: number; onSay: (text: string) => void; busy: boolean }) {
  const mark = useScanMark(`tile-${tile.key}`);
  const showText = tile.text.replace(/\.$/, "") !== tile.title;
  return (
    <button
      type="button"
      className={`tile-say tile-say--h${(index % 3) + 1}`}
      onClick={() => !busy && onSay(tile.text)}
      aria-disabled={busy || undefined}
      aria-describedby={showText ? `say-${tile.key}` : undefined}
      {...mark}
    >
      <span className="tile-say__icon" aria-hidden="true">
        <Icon name="speech" size="100%" />
      </span>
      <span className="tile-say__title">{tile.title}</span>
      {showText && (
        <span className="tile-say__text" id={`say-${tile.key}`}>
          “{tile.text}”
        </span>
      )}
      {tile.own && <span className="tile-say__own">Yours</span>}
    </button>
  );
}

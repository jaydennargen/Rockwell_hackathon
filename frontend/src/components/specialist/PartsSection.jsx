import { pct } from "../../lib/format.js";
import Section from "../Section.jsx";

export default function PartsSection({ parts }) {
  return (
    <Section title="Parts to pre-stage" note="Specialists only">
      {parts.length === 0 ? (
        <p className="muted">Not enough repair history to suggest parts.</p>
      ) : (
        <table className="ledger ledger-compact">
          <thead>
            <tr>
              <th scope="col">Part</th>
              <th scope="col" className="num">Used in</th>
            </tr>
          </thead>
          <tbody>
            {parts.map((p) => (
              <tr key={p.part}>
                <td>{p.part}</td>
                <td className="num">
                  {p.n > 0 ? `${pct(p.freq)} of ${p.n} past repairs` : "Added by specialist"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Section>
  );
}

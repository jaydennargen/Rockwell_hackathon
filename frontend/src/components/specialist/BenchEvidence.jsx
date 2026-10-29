import Section from "../Section.jsx";

export default function BenchEvidence({ items }) {
  return (
    <Section title="Bench measurements" note="From the intake test station">
      <table className="ledger ledger-compact">
        <thead>
          <tr>
            <th scope="col">Measurement</th>
            <th scope="col" className="num">Value</th>
            <th scope="col" className="num">Spec</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {items.map((m, i) => (
            <tr key={i}>
              <td>{m.name.replace(/_/g, " ")}</td>
              <td className="num">
                {m.value} {m.unit}
              </td>
              <td className="num">
                {m.spec_min ?? "—"} to {m.spec_max ?? "—"}
              </td>
              <td className={m.pass === false ? "txt-failed" : m.pass ? "txt-ok" : ""}>
                {m.pass == null ? "No spec" : m.pass ? "In spec" : "Out of spec"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

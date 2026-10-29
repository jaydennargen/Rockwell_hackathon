// One row of the report: label column on the left, content on the right (like a printed repair report).
export default function Section({ title, note, children, tone }) {
  return (
    <section className={`rsec${tone ? ` rsec-${tone}` : ""}`}>
      <div className="rsec-label">
        <h2>{title}</h2>
        {note && <p className="rsec-note">{note}</p>}
      </div>
      <div className="rsec-body">{children}</div>
    </section>
  );
}

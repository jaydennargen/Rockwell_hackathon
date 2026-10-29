import { useState } from "react";
import { useNavigate } from "react-router-dom";
import * as api from "../api/client.js";
import { nextSample } from "../lib/samples.js";

const EMPTY = {
  order_number: "", line_number: 1000, catalog: "", part_number: "", part_description: "",
  serial_number: "", depot: "", received_date: "", failure_details: "", additional_info: "",
};

function Field({ label, hint, required, children }) {
  return (
    <label className="field">
      <span>
        {label}
        {required && <em className="req"> required</em>}
      </span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export default function OrderForm() {
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const nav = useNavigate();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = { ...f, line_number: Number(f.line_number) || 1000 };
    for (const k of ["serial_number", "depot", "received_date", "additional_info"]) if (!body[k]) body[k] = null;
    try {
      const { order_id } = await api.createOrder(body);
      nav(`/requests/${order_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <form className="order-form" onSubmit={submit}>
      <div className="form-toolbar">
        <button type="button" className="btn-quiet" onClick={() => setF(nextSample())}>
          Fill with a sample order
        </button>
      </div>

      <fieldset>
        <legend>Unit</legend>
        <div className="grid-2">
          <Field label="Catalog number" required>
            <input required value={f.catalog} onChange={set("catalog")} placeholder="R1394CAM75IH/C" />
          </Field>
          <Field label="Part number">
            <input value={f.part_number} onChange={set("part_number")} />
          </Field>
          <Field label="Description">
            <input value={f.part_description} onChange={set("part_description")} />
          </Field>
          <Field label="Serial number" hint="Used to find earlier repairs of the same unit.">
            <input value={f.serial_number} onChange={set("serial_number")} />
          </Field>
        </div>
      </fieldset>

      <fieldset>
        <legend>Order</legend>
        <div className="grid-4">
          <Field label="SAP order number" required>
            <input required inputMode="numeric" value={f.order_number} onChange={set("order_number")} />
          </Field>
          <Field label="Line">
            <input inputMode="numeric" value={f.line_number} onChange={set("line_number")} />
          </Field>
          <Field label="Depot">
            <input value={f.depot} onChange={set("depot")} placeholder="P1100" />
          </Field>
          <Field label="Date received">
            <input type="date" value={f.received_date} onChange={set("received_date")} />
          </Field>
        </div>
      </fieldset>

      <fieldset>
        <legend>What's wrong</legend>
        <Field
          label="Failure description"
          required
          hint="Fault codes, symptoms, and when it happens. More detail means a faster, more confident report."
        >
          <textarea required rows={5} value={f.failure_details} onChange={set("failure_details")} />
        </Field>
        <Field label="Additional information">
          <textarea rows={2} value={f.additional_info} onChange={set("additional_info")} />
        </Field>
      </fieldset>

      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="row-actions">
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Submitting" : "Submit for triage"}
        </button>
      </div>
    </form>
  );
}

import BulkUpload from "../components/BulkUpload.jsx";
import OrderForm from "../components/OrderForm.jsx";

export default function NewRequestPage() {
  return (
    <div className="new-page">
      <div className="page-head">
        <h1>New repair request</h1>
      </div>
      <p className="page-intro">
        Enter the SAP repair order for one unit. You'll get a triage report in a few seconds, or a note that a
        specialist is checking it.
      </p>
      <OrderForm />
      <BulkUpload />
    </div>
  );
}

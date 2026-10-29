// Real orders from the provided SAP extract, for "Fill with a sample order".
// Order numbers get a random suffix so repeated demos don't collide (409).
const BASE = [
  {
    catalog: "R1394CAM75IH/C", part_number: "PN-C74863",
    part_description: "MOD AXIS INTL HTSNK 15KW 35.0A CONT", serial_number: "1JAP5JK8", depot: "P1100",
    failure_details: "AXIS FAULT E19, FAN NOISY AND RUNNING SLOW. UNIT OVERHEATS AFTER 20 MIN.",
  },
  {
    catalog: "RMPLB330PMK74AA/A", part_number: "",
    part_description: "MP-Series MPL 480V AC Rotary Servo Motor", serial_number: "326193834", depot: "P4080",
    failure_details: "BAD BEARING, GRINDING NOISE UNDER LOAD. ENCODER ERRORS INTERMITTENT.",
  },
  {
    catalog: "R2711PT6C21D8S/B", part_number: "",
    part_description: "PanelView Plus 7 Standard 600", serial_number: "DE0AI4JH", depot: "P1190",
    failure_details: "UNKNOWN FAILURE Serial Number: DE0AI4JH Ship/End Customer PO: 33469",
  },
];

let i = 0;
export function nextSample() {
  const s = BASE[i++ % BASE.length];
  const today = new Date().toISOString().slice(0, 10);
  return {
    order_number: String(67100000 + Math.floor(Math.random() * 89999)),
    line_number: 1000, received_date: today, additional_info: "", ...s,
  };
}

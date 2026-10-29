# hardware/ (WS7, stretch)

Intake bench tester: Spartan-7 Urbana fan-tach counter -> JSON lines over UART -> `bridge/bridge.py`
-> `POST /api/orders/{id}/evidence` with `X-Device-Token`. See ARCHITECTURE.md §8.

Wiring: the fan tach output is open-collector. Pull it up to 3.3 V on the FPGA side.
Never connect the fan's 12 V supply to an FPGA pin.

Message format (one per line):
    {"name": "fan_rpm", "value": 3120, "unit": "rpm"}

Try the endpoint without hardware:
    curl -X POST localhost:8000/api/orders/66650692-1000/evidence \
      -H "Content-Type: application/json" -H "X-Device-Token: dev-device-token" \
      -d '{"source":"bench-01","measurements":[{"name":"fan_rpm","value":3100,"unit":"rpm","spec_min":4200}]}'

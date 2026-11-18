"""Uji main.py Wokwi (MicroPython) dengan perangkat tiruan.
Pemakaian: python tests/sim_wokwi_micropython.py utara|selatan"""
import os, sys, json
import numpy as np, cv2
from PIL import Image

zona = sys.argv[1] if len(sys.argv) > 1 else "utara"
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(base, "tests"))
sys.path.insert(0, os.path.join(base, "wokwi-micropython", zona))
import fake_mp as F
F.install()
import config as C
import main

F.reset_hw(C.ECHO, C.TFT_CS)
S = F.SERVER
fails = []
def check(name, cond, info=""):
    print(("  OK   " if cond else "  GAGAL"), name, ("" if cond else "-> " + str(info)))
    if not cond: fails.append(name)

def near(c, ref, tol=12): return all(abs(int(a) - int(b)) <= tol for a, b in zip(c, ref))
def status_px(i): return F.HW.panels[C.TFT_CS[i]].img[300, 8]        # warna bar status
def lamp(i): return F.HW.pixels.px[C.PIX[i]]

print(f"== Zona {C.ZONA} ({C.N} meja) ==")
node = main.Node()
main.connect_wifi(node.lcd)

print("[1] Tampilan awal tiap layar")
aru = cv2.QRCodeDetectorAruco()
for i in range(C.N):
    img = F.HW.panels[C.TFT_CS[i]].img
    big = cv2.resize(img, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
    txt = aru.detectAndDecode(cv2.cvtColor(big, cv2.COLOR_RGB2GRAY))[0]
    check(f"layar {C.CODE[i]}: QR terbaca = kode meja", txt == C.QR_BASE + C.CODE[i], repr(txt))
    check(f"layar {C.CODE[i]}: header biru", near(img[5, 5], (25, 40, 90)), img[5, 5])
    check(f"layar {C.CODE[i]}: status awal MENUNGGU (abu)", near(status_px(i), (90, 90, 90)), status_px(i))
check("LCD baris 1 saat boot", F.HW.lcd.text()[0].startswith("Zona " + C.ZONA), F.HW.lcd.text())

print("[2] Semua meja kosong")
node.step()
check("semua lampu hijau", all(near(lamp(i), (0, 37, 12), 2) for i in range(C.N)), [lamp(i) for i in range(C.N)])
check("semua layar hijau TERSEDIA", all(near(status_px(i), (0, 140, 60)) for i in range(C.N)))
check("LCD: jumlah kosong", F.HW.lcd.text()[0].rstrip() == f"{C.ZONA[:3]} {C.N}/{C.N} kosong", F.HW.lcd.text())
check("LCD: Semua aman", F.HW.lcd.text()[1].rstrip() == "Semua aman", F.HW.lcd.text())
reqs = S.requests[-C.N:]
check("tiap meja dikirim sekali ke URL & header benar",
      [r[1]["code"] for r in reqs] == list(C.CODE) and all(r[0] == C.SERVER_URL and r[2].get("x-device-key") == C.DEVICE_KEY
                                                          and r[2].get("Content-Type") == "application/json" for r in reqs))
check("present=false & distance 400.0 saat tidak ada orang", all(r[1]["present"] is False and r[1]["distance"] == 400.0 for r in reqs), reqs[0][1])

print("[3] Layar tidak digambar ulang kalau status tidak berubah")
before = {cs: p.bytes_in for cs, p in F.HW.panels.items()}
node.step()
check("tidak ada byte SPI baru ke layar", all(F.HW.panels[cs].bytes_in == before[cs] for cs in before))

print("[4] Orang duduk di meja 3 tapi belum scan QR (jarak 30 cm)")
k = min(2, C.N - 1); F.HW.sensors[C.ECHO[k]] = 30.0
node.step()
r = [x for x in S.requests[-C.N:] if x[1]["code"] == C.CODE[k]][0][1]
check("dikirim present=true, jarak ~30", r["present"] is True and abs(r["distance"] - 30) < 1, r)
check("lampu kuning", near(lamp(k), (62, 43, 0), 2), lamp(k))
check("layar kuning SCAN QR!", near(status_px(k), (235, 170, 0)), status_px(k))
check("belum alarm (masih masa tenggang)", F.HW.lcd.text()[1].rstrip() == "Semua aman" and not F.HW.beeps, (F.HW.lcd.text(), F.HW.beeps))
check("meja lain tetap hijau", all(near(lamp(i), (0, 37, 12), 2) for i in range(C.N) if i != k))

print("[5] Lewat 10 detik tanpa scan -> alarm")
F.CLOCK.ms += 11000
node.step()
check("LCD menampilkan SCAN QR + meja", F.HW.lcd.text()[1].rstrip() == "SCAN QR: " + C.CODE[k][3:], F.HW.lcd.text())
check("buzzer berbunyi 3 kali @1 kHz", len(F.HW.beeps) == 3 and all(b[0] == 1000 for b in F.HW.beeps), F.HW.beeps)
check("LCD: jumlah kosong berkurang satu", F.HW.lcd.text()[0].rstrip() == f"{C.ZONA[:3]} {C.N-1}/{C.N} kosong", F.HW.lcd.text())

print("[6] Mahasiswa scan QR (server: occupied)")
S.occupied.add(C.CODE[k]); F.HW.beeps.clear()
node.step()
check("lampu merah", near(lamp(k), (62, 6, 9), 2), lamp(k))
check("layar merah DIPAKAI", near(status_px(k), (190, 25, 40)), status_px(k))
check("alarm berhenti", F.HW.lcd.text()[1].rstrip() == "Semua aman" and not F.HW.beeps, (F.HW.lcd.text(), F.HW.beeps))
check("timer tenggang direset", node.since[k] is None)

print("[7] Gangguan server / jaringan")
S.mode = "forbidden"; node.step()
check("HTTP 403 -> lampu mati & layar OFFLINE", all(lamp(i) == (0, 0, 0) for i in range(C.N)) and near(status_px(0), (90, 90, 90)))
S.mode = "boom"; node.step()
check("exception jaringan tidak membuat program berhenti", True)
S.mode = "normal"; node.step()
check("pulih otomatis setelah server normal", near(lamp(0), (0, 37, 12), 2) and near(status_px(k), (190, 25, 40)))

print("[8] run() penuh dari awal")
F.reset_hw(C.ECHO, C.TFT_CS); S.requests.clear(); S.occupied.clear()
main.run(max_loops=2)
check("run(max_loops=2) mengirim 2 x N request", len(S.requests) == 2 * C.N, len(S.requests))

# simpan tangkapan layar untuk dilihat
os.makedirs("/tmp/shots", exist_ok=True)
F.reset_hw(C.ECHO, C.TFT_CS); S.requests.clear(); S.occupied = {C.CODE[1]}
node2 = main.Node(); F.HW.sensors[C.ECHO[0]] = 30.0; F.HW.sensors[C.ECHO[2]] = 30.0
node2.step()
shots = [F.HW.panels[C.TFT_CS[i]].img for i in range(3)]
Image.fromarray(np.hstack(shots)).save(f"/tmp/shots/layar_{zona}.png")
print("\nHASIL:", "SEMUA LULUS" if not fails else f"{len(fails)} GAGAL: {fails}")
sys.exit(1 if fails else 0)

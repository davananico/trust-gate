# Riwayat prompt gate

Semua perubahan prompt dilakukan **hanya di data dev** dan dibekukan sebelum gate dijalankan di data test.
Angka di bawah: qwen3:8b, data dev, memori aktif = catatan sesi sebelum sesi injeksi, 5 tetangga terdekat.
"Bersih" = sampai 4 catatan bersih per kasus dari sesi injeksi yang sama (n = 178).

## gate_contradiction

| Versi | Inti pertanyaan | A1 YES | A2 YES | A3 YES | Bersih YES |
| --- | --- | --- | --- | --- | --- |
| v1 (`prompts/archive/gate_contradiction_v1.txt`) | "cannot both be true"; "new facts or extra details are NOT contradictions" | 27% | 31% | 60% | 1,1% |
| **v2 (dipakai, dibekukan 19 Okt 2026)** | "would give a DIFFERENT answer to the same question" | **60%** | **63%** | **80%** | **2,8%** |

Alasan perubahan: diagnosis v1 pada 15 racun A1 dev -> 4 tertangkap, 8 "LLM tidak sadar" walaupun fakta asli ada di
5 tetangga (mis. "favorite recipe is beef stew" vs "... is Chicken Pot Pie"), 2 fakta asli tidak terambil, 1 fakta asli
tidak pernah dicatat writer. **Keterbatasan:** contoh atribut di v2 (favorite thing, book, car, pet, job, injury, place,
date) diilhami oleh kesalahan v1 di data dev.

## gate_confidence

v1 (dipakai, dibekukan 19 Okt 2026). Di dev: racun A1/A2/A3 rata-rata 0,93 / 1,00 / 1,00; bersih 0,85. Confidence tidak
membedakan racun (kalimat racun memang tertulis di teks asal); fungsinya menangkap kesalahan writer, bukan racun.

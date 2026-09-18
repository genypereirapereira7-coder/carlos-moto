/** Marcas e modelos que a loja trabalha — lista fixa, pra cadastro e edição
 * nunca dependerem de digitar o nome certo. */

export const MARCAS_E_MODELOS = {
  Honda: [
    "Biz 100 KS", "Biz 100 ES", "Biz 100 +", "Biz 100i", "Biz 110i",
    "Biz 125 KS", "Biz 125 ES", "Biz 125 +", "Biz 125 EX", "Biz 125i",
    "Pop 100", "Pop 110i", "Pop 110i ES",
    "Lead 110", "Elite 125",
    "PCX 150 DLX", "PCX 150 Sport", "PCX 150 ABS",
    "PCX 160 CBS", "PCX 160 ABS", "PCX 160 DLX",
    "SH 150i", "SH 150i DLX", "SH 300i", "SH 300i Sport", "ADV 150", "ADV 350",
    "CG 125 Titan KS", "CG 125 Titan ES", "CG 125 Titan KSE",
    "CG 125 Fan", "CG 125i Fan", "CG 125 Cargo", "CG 125i Cargo",
    "CG 150 Titan KS", "CG 150 Titan ES", "CG 150 Titan ESD", "CG 150 Titan EX",
    "CG 150 Fan ESi", "CG 150 Fan ESDi", "CG 150 Job", "CG 150 Sport", "CG 150 Start",
    "CG 160 Titan", "CG 160 Fan", "CG 160 Start", "CG 160 Cargo",
    "NXR 125 Bros KS", "NXR 125 Bros ES",
    "NXR 150 Bros KS", "NXR 150 Bros ES", "NXR 150 Bros ESD", "NXR 150 Bros Mix",
    "NXR 160 Bros ESDD", "NXR 160 Bros SE",
    "CBX 200 Strada", "XR 200R",
    "CBX 250 Twister", "CB 300R", "CB 300R ABS",
    "CB 250F Twister CBS", "CB 250F Twister ABS",
    "CB 300F Twister CBS", "CB 300F Twister ABS",
    "XR 250 Tornado", "XRE 300", "XRE 300 ABS", "XRE 300 Rally", "XRE 300 Adventure",
    "XRE 300 Sahara Standard", "XRE 300 Sahara Rally", "XRE 300 Sahara Adventure",
    "NX 350 Sahara", "NX 400 Falcon", "NX 400i Falcon",
    "XRE 190 ABS", "XRE 190 Adventure",
    "CB 500", "CB 500F", "CB 500X", "CB 500 Hornet", "NX 500",
    "CB 600F Hornet Carburada", "CB 600F Hornet Injetada", "CB 600F Hornet ABS",
    "CBX 750F Indy", "CB 650F", "CB 650R Neo Sports Café",
    "CBR 600F", "CBR 600RR", "CBR 650F", "CBR 650R",
    "NC 700X", "NC 750X", "NC 750X DCT",
    "XL 700V Transalp", "XL 700V Transalp ABS", "XL 750 Transalp",
    "CRF 1000L Africa Twin", "CRF 1000L Africa Twin Adventure Sports",
    "CRF 1100L Africa Twin", "CRF 1100L Africa Twin DCT",
    "CRF 1100L Africa Twin Adventure Sports DCT", "X-ADV 750",
    "CB 900F Hornet", "CB 1000R", "CB 1000R Black Edition",
    "CBR 1000RR Fireblade", "CBR 1000RR-R Fireblade SP",
    "VT 600C Shadow", "Shadow 750", "Shadow 750 ABS",
    "VFR 1200F", "VFR 1200X Crosstourer",
    "GL 1800 Gold Wing", "GL 1800 Gold Wing Tour DCT",
    "CRF 230F", "CRF 250F",
  ],
  Yamaha: [
    "Neo 125", "Fluo 125", "NMax 160", "Aerox 160", "XMax 250",
    "Factor 125i", "Factor 150", "Fazer FZ15", "Fazer FZ25",
    "R15", "R3", "R7", "Crosser 150", "Lander 250",
    "Tracer 7", "Tracer 9 GT", "MT-03", "MT-07", "MT-09",
  ],
  Mottu: ["Mottu Sport 110i", "Mottu 160"],
  Shineray: [
    "Jet 50", "Jet 125", "Phoenix 50", "Ray 50", "XY 50", "Worker 125",
    "JEF 150", "SHI 175", "Storm 200", "SBM 250T", "Free 150", "Urban 150",
  ],
  Avelloz: ["AZ1"],
  Bajaj: ["Pulsar N150", "Pulsar N160", "Dominar 160", "Dominar 200", "Dominar 400"],
  "Royal Enfield": [
    "Hunter 350", "Classic 350", "Meteor 350", "Bullet 350", "Scram 411",
    "Himalayan 450", "Interceptor 650", "Continental GT 650",
    "Super Meteor 650", "Shotgun 650",
  ],
  "BMW Motorrad": [
    "G 310 R", "G 310 GS", "F 800 GS", "F 900 GS", "F 900 R",
    "R 12", "R 18", "R 1300 GS", "S 1000 RR", "M 1000 RR",
  ],
  Kawasaki: [
    "Ninja 300", "Ninja 400", "Ninja 500", "Ninja 650", "Ninja ZX-4R",
    "Ninja ZX-6R", "Ninja ZX-10R", "Z400", "Z500", "Z650", "Z900",
    "Versys-X 300", "Versys 650", "Versys 1000", "Vulcan S 650",
  ],
  Triumph: [
    "Speed 400", "Scrambler 400X", "Trident 660", "Tiger Sport 660",
    "Street Triple 765", "Tiger 900", "Tiger 1200", "Bonneville T100",
    "Bonneville T120", "Scrambler 900", "Scrambler 1200",
    "Speed Twin 900", "Speed Twin 1200", "Rocket 3",
  ],
  "Harley-Davidson": [
    "Nightster Special", "Sportster S", "Low Rider S", "Low Rider ST",
    "Fat Boy", "Heritage Classic", "Breakout", "Street Glide",
    "Road Glide", "Pan America 1250 Special",
  ],
};

/**
 * Modelos que saíram de linha mas ainda rodam — e chegam na loja como moto
 * usada. Ficam separados dos atuais pra lista não virar uma parede de nomes:
 * no cadastro aparecem num grupo próprio, "Modelos antigos".
 *
 * Um item é o nome, ou `[nome, nota]`: a nota aparece na lista pra ajudar a
 * escolher a geração certa, mas o que fica gravado na moto é só o nome.
 * `XJ6 N / XJ6 F` e `V-Max 1200 / 1800` viraram dois itens cada — são motos
 * diferentes, e a ficha precisa dizer qual das duas é.
 */
export const MODELOS_ANTIGOS = {
  Honda: [
    "CG 125 Titan", "CG 150 Titan", "CBX 250 Twister", "XR 250 Tornado", "NX 400 Falcon",
    ["CB 500", "bicilíndrica carburada antiga"],
    "CB 600F Hornet",
    ["XRE 300", "antiga, antes da Sahara"],
    "CBX 200 Strada", "XR 200R", "C100 Biz", "Lead 110", "PCX 150", "SH 150i", "SH 300i",
    ["NX 350 Sahara", "vendida até o início dos anos 2000"],
    "Shadow 600", "Shadow 750", "XL 700V Transalp",
    ["CB 1000R", "geração antiga, Barracuda"],
    "VFR 1200X Crosstourer", "CTX 700",
  ],
  Yamaha: [
    "YBR 125", "XTZ 125",
    ["XTZ 250X", "supermoto"],
    "XT 225", "XT 600E", "XT 660R", "XTZ 750 Super Ténéré", "Ténéré 250", "Ténéré 660",
    ["Fazer 250", "gerações antigas, farol redondo"],
    "YZF-R1", "YZF-R6", "Crypton 105", "Crypton 115", "Neo AT 115", "Fazer 600",
    "XJ6 N", "XJ6 F", "MT-01", "V-Max 1200", "V-Max 1800",
    "Midnight Star 950", "Drag Star 650",
  ],
};

export const MARCAS = Object.keys(MARCAS_E_MODELOS);

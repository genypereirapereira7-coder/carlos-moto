/** Marcas e modelos que a loja trabalha — lista fixa, pra cadastro e edição
 * nunca dependerem de digitar o nome certo. */

export const MARCAS_E_MODELOS = {
  Honda: [
    "Pop 110i", "Biz 110i", "Biz 125", "Elite 125", "PCX 160", "ADV 150",
    "CG 160 Titan", "CG 160 Fan", "CG 160 Start", "CG 160 Cargo",
    "NXR 160 Bros", "XRE 190", "CRF 250F", "CB 300F Twister", "XRE 300 Sahara",
    "CB 500F", "CB 500X", "CBR 650R", "CB 650R", "NC 750X",
    "CRF 1100L Africa Twin", "GL 1800 Gold Wing",
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

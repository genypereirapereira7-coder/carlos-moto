"""Clonador do sistema antigo — o programa que roda no computador do cliente.

Dois cliques e acabou: procura o sistema antigo no disco, escolhe o mais
provável, manda pro Carlos Moto na nuvem e mostra o que copiou. Ninguém
escolhe arquivo, ninguém digita caminho.

**Por que isto existe como programa, e não como botão no site.** Uma página da
internet não pode ler o disco de quem a abre — o navegador proíbe, e é a regra
que impede qualquer site de ler os seus documentos. Só um programa rodando
naquela máquina consegue. Este é esse programa.

Ele não mexe em nada do sistema antigo: abre em modo de leitura, manda uma
cópia pro espelho na nuvem e vai embora.

Configuração, embutida no `.exe` na hora de empacotar (ou por variável de
ambiente, pra testar):

    CARLOSMOTO_ENDERECO   https://carlos-moto-production.up.railway.app
    CARLOSMOTO_CHAVE      a chave de acesso do dono
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# Preenchidos no empacotamento. Sem eles, o programa pergunta.
ENDERECO = os.environ.get("CARLOSMOTO_ENDERECO", "")
CHAVE = os.environ.get("CARLOSMOTO_CHAVE", "")

# O motor da migração vive no backend do projeto; o empacotador leva junto.
_AQUI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
for candidato in (_AQUI / "backend", _AQUI.parent / "backend"):
    if (candidato / "app").is_dir():
        sys.path.insert(0, str(candidato))
        break

from app.servicos.migracao import procurar_sistemas_antigos  # noqa: E402


def diga(texto: str = "") -> None:
    print(texto, flush=True)


def _pedir(metodo: str, caminho: str, corpo=None, token: str = "", partes=None):
    """Uma chamada à API do sistema novo. Sem biblioteca extra: o `.exe` tem
    que ser um arquivo só, e cada dependência é mais coisa pra empacotar."""
    url = ENDERECO.rstrip("/") + caminho
    cabecalhos = {}
    dados = None

    if partes is not None:
        limite = f"----carlosmoto{uuid.uuid4().hex}"
        pedaços = []
        for nome_campo, arquivo in partes:
            pedaços.append(f"--{limite}\r\n".encode())
            pedaços.append(
                f'Content-Disposition: form-data; name="{nome_campo}"; '
                f'filename="{arquivo.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
            )
            pedaços.append(arquivo.read_bytes())
            pedaços.append(b"\r\n")
        pedaços.append(f"--{limite}--\r\n".encode())
        dados = b"".join(pedaços)
        cabecalhos["Content-Type"] = f"multipart/form-data; boundary={limite}"
    elif corpo is not None:
        dados = json.dumps(corpo).encode()
        cabecalhos["Content-Type"] = "application/json"

    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"

    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=600) as resposta:
            return json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        detalhe = json.loads(erro.read() or b"{}").get("detail", erro.reason)
        raise RuntimeError(f"{erro.code}: {detalhe}") from None
    except urllib.error.URLError as erro:
        raise RuntimeError(f"não deu pra falar com o sistema novo ({erro.reason})") from None


def main() -> int:
    global ENDERECO, CHAVE

    diga("=" * 62)
    diga("  CARLOS MOTO - copiar o sistema antigo para o sistema novo")
    diga("=" * 62)
    diga()

    if not ENDERECO:
        ENDERECO = input("  Endereço do sistema novo: ").strip()
    if not CHAVE:
        CHAVE = input("  Chave de acesso: ").strip()

    diga("  Entrando no sistema novo...")
    sessao = _pedir("POST", "/auth/parear", {"chave": CHAVE, "dispositivo": "clonador do sistema antigo"})
    token = sessao["acesso"]
    diga(f"  ok, {sessao['nome']}")
    diga()

    diga("  Procurando o sistema antigo neste computador...")
    achados = procurar_sistemas_antigos()
    if not achados:
        diga("  Nao achei nenhum banco de sistema antigo nas pastas de sempre.")
        diga("  Rode de novo com a pasta: agente.exe C:\\Caminho\\Do\\Sistema")
        return 1

    for posicao, achado in enumerate(achados[:5]):
        marca = "  -->" if posicao == 0 else "     "
        diga(f"{marca} {achado['tipo']:<6} {achado['bytes'] / 1024 / 1024:>8.1f} MB  "
             f"{achado['modificado']}  {achado['caminho']}")
    diga()

    escolhido = Path(achados[0]["caminho"])
    arquivos = sorted(p for p in escolhido.iterdir() if p.is_file()) if escolhido.is_dir() else [escolhido]
    diga(f"  Copiando: {escolhido}")
    diga(f"  {len(arquivos)} arquivo(s), {sum(a.stat().st_size for a in arquivos) / 1024 / 1024:.1f} MB")
    diga("  (isso nao altera nada no sistema antigo — so le)")
    diga()

    envio = _pedir("POST", "/migracao/enviar", token=token,
                   partes=[("arquivos", arquivo) for arquivo in arquivos])
    lote = envio["lote_id"]
    diga(f"  Enviado. Lote {lote}. Copiando na nuvem...")

    situacao = "RODANDO"
    while situacao == "RODANDO":
        time.sleep(2)
        estado = _pedir("GET", f"/migracao/lotes/{lote}", token=token)
        situacao = estado["situacao"]

    diga()
    for nome, info in (estado.get("tabelas") or {}).items():
        diga(f"    {nome:<34} {info['linhas']:>9} linhas   (de {info['origem']})")
    for erro in (estado.get("erros") or []):
        diga(f"    ERRO em {erro.get('tabela') or 'origem'}: {erro.get('erro')}")
    diga()
    diga(f"  {situacao}")

    # A sessão morre junto com o programa: o aparelho do cliente não fica
    # conectado no sistema novo depois que a cópia acaba.
    try:
        _pedir("POST", "/auth/sair", {"refresh": sessao["refresh"]})
    except RuntimeError:
        pass

    return 0 if situacao == "CONCLUIDO" else 1


if __name__ == "__main__":
    try:
        codigo = main()
    except Exception as erro:  # noqa: BLE001 - é a tela final do cliente, não pode sair traceback
        diga()
        diga(f"  NAO DEU CERTO: {erro}")
        codigo = 1
    diga()
    try:
        input("  Pressione Enter para fechar...")
    except (EOFError, KeyboardInterrupt):
        # Rodando por script, sem teclado: a última coisa que o cliente vê não
        # pode ser um traceback depois de a cópia ter dado certo.
        pass
    raise SystemExit(codigo)

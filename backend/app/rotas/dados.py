"""Aba DADOS: o arquivo do sistema antigo da loja, organizado.

Só leitura depois de importado. O que precisa entrar no sistema vivo (cliente,
carnê) sai daqui por um caminho próprio, com conferência antes de gravar — não
por efeito colateral de abrir uma tela.
"""

import dataclasses
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app import dicionario_antigo as dic
from app.dependencias import SessaoDep, SoDono
from app.models.dado_antigo import LinhaAntiga, LoteAntigo
from app.servicos import busca_antiga
from app.servicos import nota_fiscal
from app.servicos import dados_antigos as servico
from app.servicos import trazer_antigo
from app.servicos import trazer_parcelas as servico_parcelas

rotas = APIRouter(prefix="/dados", tags=["dados-antigos"])

# Teto do envio. 183 CSVs de um ERP pequeno dão poucos MB; acima disso é
# arquivo errado, não sistema de loja.
_MAX_BYTES = 80 * 1024 * 1024


@rotas.get("/lotes")
async def lotes(sessao: SessaoDep, _: SoDono):
    """As importações que já foram feitas, da mais recente pra mais antiga."""
    lista = (
        await sessao.execute(select(LoteAntigo).order_by(LoteAntigo.criado_em.desc()))
    ).scalars().all()

    # O tamanho vai junto: com duas importações do mesmo sistema, a descrição e
    # a data não dizem qual é a completa e qual foi o teste.
    contagem = {
        lote_id: (tabelas, linhas)
        for lote_id, tabelas, linhas in (
            await sessao.execute(
                select(
                    LinhaAntiga.lote_id,
                    func.count(func.distinct(LinhaAntiga.tabela)),
                    func.count(),
                ).group_by(LinhaAntiga.lote_id)
            )
        ).all()
    }
    return [
        {
            "id": str(l.id),
            "descricao": l.descricao,
            "origem": l.origem,
            "criado_em": l.criado_em,
            "tabelas": contagem.get(l.id, (0, 0))[0],
            "linhas": contagem.get(l.id, (0, 0))[1],
        }
        for l in lista
    ]


@rotas.post("/importar", status_code=status.HTTP_201_CREATED)
async def importar(
    sessao: SessaoDep,
    _: SoDono,
    arquivos: list[UploadFile] = File(...),
    descricao: str = Form(...),
    origem: str | None = Form(None),
):
    """Recebe CSVs, um backup `.sql` de MySQL, ou um ZIP com eles dentro."""
    if not descricao.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Dê um nome a esta importação — é assim que você vai reconhecê-la depois",
        )

    lidos: list[tuple[str, bytes]] = []
    total = 0
    for arquivo in arquivos:
        conteudo = await arquivo.read()
        total += len(conteudo)
        if total > _MAX_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"Passou de {_MAX_BYTES // 1024 // 1024} MB no total",
            )
        lidos.append((arquivo.filename or "sem-nome", conteudo))

    resultado = await servico.importar(
        sessao, lidos, descricao=descricao.strip(), origem=(origem or "").strip() or None
    )
    if not resultado.tabelas:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nenhuma linha foi lida. Confira se são arquivos .csv com cabeçalho, ou um backup .sql.",
        )
    await sessao.commit()
    return {
        "lote_id": resultado.lote_id,
        "tabelas": len(resultado.tabelas),
        "linhas": resultado.total_linhas,
        "ignorados": resultado.ignorados,
    }


@rotas.get("/{lote_id}")
async def resumo(lote_id: uuid.UUID, sessao: SessaoDep, _: SoDono):
    """As tabelas do lote, com nome de gente e as fiscais separadas.

    A tela abre mostrando só o que diz algo sobre esta loja. Tabela de estado,
    NCM e CFOP vem de fábrica com qualquer ERP do Brasil — fica no grupo
    escondido, pra quem insistir.
    """
    lote = await sessao.get(LoteAntigo, lote_id)
    if lote is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa importação não existe")

    contagens = (
        await sessao.execute(
            select(LinhaAntiga.tabela, func.count(LinhaAntiga.id))
            .where(LinhaAntiga.lote_id == lote_id)
            .group_by(LinhaAntiga.tabela)
        )
    ).all()

    tabelas = [
        {
            "tabela": nome,
            "titulo": dic.nome_da_tabela(nome),
            "linhas": int(quantas),
            "ruido": dic.e_ruido(nome),
        }
        for nome, quantas in contagens
    ]
    tabelas.sort(key=lambda t: (dic.ordem_da_tabela(t["tabela"]), -t["linhas"]))

    return {
        "lote": {"id": str(lote.id), "descricao": lote.descricao, "origem": lote.origem,
                 "criado_em": lote.criado_em},
        "tabelas": [t for t in tabelas if not t["ruido"]],
        "fiscais": [t for t in tabelas if t["ruido"]],
    }


@rotas.post("/{lote_id}/trazer/clientes")
async def trazer_clientes(lote_id: uuid.UUID, sessao: SessaoDep, _: SoDono):
    """Cria os clientes do sistema antigo no cadastro do sistema novo.

    Pode rodar de novo sem medo: cliente que já existe (mesmo CPF) só recebe o
    que está em branco nele, e nada do que o dono digitou é sobrescrito.
    """
    resultado = await trazer_antigo.trazer_clientes(sessao, lote_id)
    await sessao.commit()
    return {
        "criados": resultado.criados,
        "completados": resultado.completados,
        "juntados": resultado.juntados,
        "descartados": resultado.descartados,
        "pulados": [
            {"codigo": p.codigo, "nome": p.nome, "motivo": p.motivo}
            for p in resultado.pulados
        ],
    }


@rotas.post("/{lote_id}/trazer/parcelas")
async def trazer_parcelas(lote_id: uuid.UUID, sessao: SessaoDep, ident: SoDono):
    """Traz as parcelas que o cliente ainda deve pra aba PARCELAS.

    Reconstrói a corrente inteira — moto, venda e carnê — porque parcela no
    sistema novo não existe solta. Pode rodar de novo: cada venda do sistema
    antigo tem identificador fixo, e a que já entrou é ignorada.
    """
    resultado = await servico_parcelas.trazer_parcelas(sessao, lote_id, ident.usuario_id)
    await sessao.commit()
    return {
        "motos": resultado.motos,
        "vendas": resultado.vendas,
        "parcelas": resultado.parcelas,
        "centavos": resultado.centavos,
        "parcelas_puladas": resultado.parcelas_puladas,
        "puladas": [
            {"numero": p.numero, "nome": p.nome, "parcelas": p.parcelas, "motivo": p.motivo}
            for p in resultado.puladas
        ],
    }


@rotas.get("/{lote_id}/nota/{numero_linha}")
async def ver_nota(
    lote_id: uuid.UUID,
    numero_linha: int,
    sessao: SessaoDep,
    _: SoDono,
    tabela: str = "xml_nfe",
):
    """Abre a nota fiscal guardada no backup, legível.

    O XML inteiro está numa coluna da tabela — sete mil caracteres que não dá
    pra ler na grade. Aqui ele vira número, data, quem emitiu, pra quem, os
    itens e o total.
    """
    linha = (
        await sessao.execute(
            select(LinhaAntiga).where(
                LinhaAntiga.lote_id == lote_id,
                LinhaAntiga.tabela == tabela.lower(),
                LinhaAntiga.numero_linha == numero_linha,
            )
        )
    ).scalars().first()
    if linha is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa nota não está nesta importação")

    try:
        nota = nota_fiscal.ler(linha.dados.get("xml"), linha.dados.get("xml_can"))
    except nota_fiscal.NotaIlegivel as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from erro
    return dataclasses.asdict(nota)


@rotas.get("/{lote_id}/{tabela}")
async def ver_tabela(
    lote_id: uuid.UUID,
    tabela: str,
    sessao: SessaoDep,
    _: SoDono,
    busca: str | None = None,
    pagina: int = 1,
    por_pagina: int = 50,
    tudo: bool = False,
):
    """As linhas de uma tabela, com colunas traduzidas e busca.

    `tudo=true` traz também as colunas escondidas. O dicionário esconde
    tributação e controle interno pra tela ficar legível, mas o dado está
    guardado — e um dia o dono vai precisar justo do campo que eu escondi.
    """
    por_pagina = max(1, min(por_pagina, 200))
    pagina = max(1, pagina)

    linhas = (
        await sessao.execute(
            select(LinhaAntiga)
            .where(LinhaAntiga.lote_id == lote_id, LinhaAntiga.tabela == tabela.lower())
            .order_by(LinhaAntiga.numero_linha)
        )
    ).scalars().all()
    if not linhas:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Essa tabela não está nesta importação")

    # Busca em memória: o lote inteiro de um ERP de loja pequena cabe, e assim
    # a busca funciona igual no SQLite e no Postgres sem SQL de JSON, que é
    # diferente nos dois. A tradução do termo (CPF com ou sem ponto, data em
    # dd/mm/aaaa) está em `servicos/busca_antiga.py`.
    alvo = busca_antiga.preparar(busca)
    if alvo:
        linhas = [l for l in linhas if busca_antiga.combina(l.dados, alvo)]

    # As colunas são a união do que apareceu, na ordem da primeira linha.
    vistas: list[str] = []
    for l in linhas[:200]:
        for c in l.dados:
            if c not in vistas:
                vistas.append(c)
    colunas = vistas if tudo else [c for c in vistas if not dic.coluna_escondida(c)]
    # A ordem do `CREATE TABLE` do ERP não é a ordem de quem lê: nome e CPF
    # primeiro, controle interno no fim. `sort` é estável, então coluna sem
    # tradução mantém a ordem do arquivo.
    colunas.sort(key=dic.ordem_da_coluna)

    total = len(linhas)
    inicio = (pagina - 1) * por_pagina
    recorte = linhas[inicio:inicio + por_pagina]

    return {
        "tabela": tabela.lower(),
        "titulo": dic.nome_da_tabela(tabela),
        "colunas": [
            {"campo": c, "titulo": t} for c, t in zip(colunas, dic.titulos(colunas))
        ],
        "linhas": [[l.dados.get(c, "") for c in colunas] for l in recorte],
        # O número da linha de cada uma, na ordem: é por ele que a tela pede
        # pra abrir a nota fiscal daquela linha.
        "numeros": [l.numero_linha for l in recorte],
        # Tem XML guardado? Então esta tabela é de nota fiscal, e cada linha
        # pode ser aberta como documento em vez de lida como grade.
        "tem_nota": any("xml" in l.dados for l in recorte),
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "escondidas": len(vistas) - len(colunas),
    }

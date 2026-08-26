#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Atualiza radar.json com:
  - 2 noticias reais sobre El Nino (Google News), publicadas nas ultimas ~60h
  - indice de chuva real (Open-Meteo) de uma cidade polo de soja/milho/cana sorteada

Roda dentro do GitHub Actions (tem acesso livre a internet, sem problema de CORS
porque e servidor, nao navegador). O front-end so le o radar.json (mesmo dominio).
"""
import html
import json
import random
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

CTX = ssl.create_default_context()

CIDADES = [
    {"nome": "SORRISO", "uf": "MT", "lat": -12.5453, "lon": -55.7217, "cultura": "SOJA · MILHO"},
    {"nome": "RIO VERDE", "uf": "GO", "lat": -17.7975, "lon": -50.9264, "cultura": "SOJA · MILHO"},
    {"nome": "SAPEZAL", "uf": "MT", "lat": -13.5427, "lon": -58.8181, "cultura": "SOJA · MILHO"},
    {"nome": "CRISTALINA", "uf": "GO", "lat": -16.7675, "lon": -47.6132, "cultura": "SOJA · MILHO"},
    {"nome": "PALOTINA", "uf": "PR", "lat": -24.2836, "lon": -53.8400, "cultura": "MILHO · SOJA"},
    {"nome": "CASCAVEL", "uf": "PR", "lat": -24.9555, "lon": -53.4552, "cultura": "SOJA · MILHO"},
    {"nome": "L.E. MAGALHÃES", "uf": "BA", "lat": -12.0956, "lon": -45.7986, "cultura": "SOJA"},
    {"nome": "BALSAS", "uf": "MA", "lat": -7.5325, "lon": -46.0357, "cultura": "SOJA"},
    {"nome": "RIBEIRÃO PRETO", "uf": "SP", "lat": -21.1775, "lon": -47.8103, "cultura": "CANA"},
    {"nome": "SERTÃOZINHO", "uf": "SP", "lat": -21.1378, "lon": -48.0175, "cultura": "CANA"},
    {"nome": "BARRETOS", "uf": "SP", "lat": -20.5572, "lon": -48.5675, "cultura": "CANA"},
    {"nome": "UBERLÂNDIA", "uf": "MG", "lat": -18.9146, "lon": -48.2754, "cultura": "SOJA · MILHO · CANA"},
]


def buscar_url(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (radar-climatico-bot)"})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
        return resp.read()


def limpar_texto(txt):
    txt = re.sub(r"<[^>]+>", "", txt or "")
    txt = html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def buscar_noticias():
    query = '"El Niño" (clima OR seca OR chuva OR safra OR agro)'
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )
    xml_bytes = buscar_url(url)
    root = ET.fromstring(xml_bytes)
    agora = datetime.now(timezone.utc)
    candidatos = []
    for item in root.iter("item"):
        titulo_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        fonte_el = item.find("source")
        if titulo_el is None or link_el is None or pub_el is None:
            continue
        try:
            data_pub = parsedate_to_datetime(pub_el.text)
            if data_pub.tzinfo is None:
                data_pub = data_pub.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        diff_horas = (agora - data_pub).total_seconds() / 3600
        if diff_horas < -2 or diff_horas > 60:
            continue
        rotulo = "HOJE" if diff_horas <= 20 else "ONTEM"

        titulo = limpar_texto(titulo_el.text)
        fonte = limpar_texto(fonte_el.text) if fonte_el is not None and fonte_el.text else None
        if fonte and titulo.endswith(" - " + fonte):
            titulo = titulo[: -(len(fonte) + 3)]
        elif not fonte and " - " in titulo:
            titulo, fonte = titulo.rsplit(" - ", 1)

        resumo = limpar_texto(desc_el.text) if desc_el is not None else ""
        # Descrição do Google News às vezes só repete "Título  Fonte" — descarta nesse caso
        if resumo and titulo and resumo.startswith(titulo):
            resumo = ""
        if len(resumo) > 140:
            resumo = resumo[:137] + "..."

        candidatos.append(
            {
                "titulo": titulo,
                "resumo": resumo or "Leia a matéria completa na fonte original.",
                "fonte": (fonte or "Google News").upper(),
                "rotuloData": rotulo,
                "link": link_el.text.strip(),
            }
        )
    random.shuffle(candidatos)
    return candidatos[:2]


def buscar_chuva():
    cidade = random.choice(CIDADES)
    url = (
        "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
        "&daily=precipitation_sum,precipitation_probability_max"
        "&timezone=America%%2FSao_Paulo&forecast_days=2" % (cidade["lat"], cidade["lon"])
    )
    dados = json.loads(buscar_url(url))
    diario = dados.get("daily", {})
    probs = diario.get("precipitation_probability_max", [])
    if not probs or probs[0] is None:
        return None
    hoje = probs[0]
    amanha = probs[1] if len(probs) > 1 else None
    seta = "↑" if (amanha is not None and amanha > hoje) else "↓"
    if hoje >= 70:
        status = "ALERTA CHUVA"
    elif hoje <= 15:
        status = "ALERTA SECA"
    else:
        status = cidade["cultura"]
    return {
        "cidade": cidade["nome"],
        "uf": cidade["uf"],
        "valor": round(hoje),
        "seta": seta,
        "status": status,
    }


def main():
    saida = {"atualizado_em": datetime.now(timezone.utc).isoformat()}
    try:
        saida["noticias"] = buscar_noticias()
    except Exception as e:
        print("Falha ao buscar noticias:", e, file=sys.stderr)
        saida["noticias"] = []
    try:
        saida["chuva"] = buscar_chuva()
    except Exception as e:
        print("Falha ao buscar chuva:", e, file=sys.stderr)
        saida["chuva"] = None

    with open("radar.json", "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    print("radar.json atualizado:", saida)


if __name__ == "__main__":
    import urllib.parse
    main()

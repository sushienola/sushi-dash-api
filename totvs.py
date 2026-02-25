import requests
import json
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta

TOTVS_BASE = "https://chefwebcloud.chef.totvs.com.br"
SERIAL = "96736989"
LOGIN = "larissa.sushileblon"
SENHA = "Senha280@"


def get_token():
    url = f"{TOTVS_BASE}/api/Token/GerarToken"
    # Tenta variações de payload que a API TOTVS Chef pode aceitar
    payloads = [
        {"NumeroSerialLoja": SERIAL, "Login": LOGIN, "Senha": SENHA},
        {"numeroSerialLoja": SERIAL, "login": LOGIN, "senha": SENHA},
        {"Serial": SERIAL, "Usuario": LOGIN, "Senha": SENHA},
        {"serialLoja": SERIAL, "usuario": LOGIN, "senha": SENHA},
    ]
    for payload in payloads:
        r = requests.post(url, json=payload, timeout=30, verify=True)
        ct = r.headers.get("Content-Type", "")
        if "html" in ct or r.text.strip().startswith("<"):
            continue
        try:
            data = r.json()
            token = (
                data.get("token")
                or data.get("Token")
                or data.get("access_token")
                or data.get("AccessToken")
                or (data.get("data", {}) or {}).get("token")
            )
            if token and not token.strip().startswith("<"):
                return token
        except Exception:
            continue
    raise Exception("Não foi possível autenticar na API TOTVS. Verifique as credenciais.")


def get_dates(days=30):
    end = datetime.today()
    start = end - timedelta(days=days)
    return start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")


def fetch_capa_venda(token, data_ini, data_fim):
    url = f"{TOTVS_BASE}/Chefwebapi/api/CapaVenda/ListPorDataMovimento"
    payload = {
        "NumeroSerialLoja": SERIAL,
        "DataInicio": data_ini,
        "DataFim": data_fim,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=60, verify=True)
    r.raise_for_status()
    return r.json()


def fetch_itens_venda(token, data_ini, data_fim):
    url = f"{TOTVS_BASE}/Chefwebapi/api/ItemVenda/ListPorDataMovimento"
    payload = {
        "NumeroSerialLoja": SERIAL,
        "DataInicio": data_ini,
        "DataFim": data_fim,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=60, verify=True)
    r.raise_for_status()
    return r.json()


def fetch_mesas(token):
    url = f"{TOTVS_BASE}/Chefwebapi/api/Mesa/ListMesas"
    payload = {"NumeroSerialLoja": SERIAL}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=30, verify=True)
    r.raise_for_status()
    return r.json()


def processar_dashboard(capa, itens, mesas):
    # --- Vendas totais ---
    total_vendas = 0
    total_pedidos = 0
    formas_pagamento = {}

    for venda in (capa or []):
        valor = venda.get("ValorTotal") or venda.get("valorTotal") or 0
        total_vendas += float(valor)
        total_pedidos += 1
        forma = venda.get("DescricaoFormaPagamento") or venda.get("FormaPagamento") or "Outros"
        formas_pagamento[forma] = formas_pagamento.get(forma, 0) + float(valor)

    # --- Produtos mais vendidos ---
    produtos = {}
    for item in (itens or []):
        nome = item.get("DescricaoProduto") or item.get("Produto") or "Desconhecido"
        qtd = float(item.get("Quantidade") or item.get("quantidade") or 0)
        valor = float(item.get("ValorTotal") or item.get("valorTotal") or 0)
        if nome not in produtos:
            produtos[nome] = {"quantidade": 0, "valor": 0}
        produtos[nome]["quantidade"] += qtd
        produtos[nome]["valor"] += valor

    top_produtos = sorted(produtos.items(), key=lambda x: x[1]["quantidade"], reverse=True)[:10]

    # --- Mesas abertas ---
    mesas_abertas = []
    for mesa in (mesas or []):
        status = mesa.get("Status") or mesa.get("status") or ""
        if str(status) in ["1", "Aberta", "aberta", "ABERTA", "Ocupada"]:
            mesas_abertas.append({
                "numero": mesa.get("NumeroMesa") or mesa.get("Numero") or "?",
                "valor": float(mesa.get("ValorTotal") or mesa.get("valor") or 0),
                "abertura": mesa.get("DataAbertura") or mesa.get("dataAbertura") or "",
            })

    return {
        "total_vendas": round(total_vendas, 2),
        "total_pedidos": total_pedidos,
        "ticket_medio": round(total_vendas / total_pedidos, 2) if total_pedidos > 0 else 0,
        "formas_pagamento": [{"nome": k, "valor": round(v, 2)} for k, v in formas_pagamento.items()],
        "top_produtos": [{"nome": k, "quantidade": v["quantidade"], "valor": round(v["valor"], 2)} for k, v in top_produtos],
        "mesas_abertas": mesas_abertas,
        "mesas_abertas_count": len(mesas_abertas),
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            token = get_token()
            data_ini, data_fim = get_dates(30)
            capa = fetch_capa_venda(token, data_ini, data_fim)
            itens = fetch_itens_venda(token, data_ini, data_fim)
            try:
                mesas = fetch_mesas(token)
            except Exception:
                mesas = []
            resultado = processar_dashboard(capa, itens, mesas)
            resultado["periodo"] = f"{data_ini} → {data_fim}"
            resultado["status"] = "ok"
            self.wfile.write(json.dumps(resultado).encode())
        except Exception as e:
            self.wfile.write(json.dumps({"status": "erro", "mensagem": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

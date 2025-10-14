import requests
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime
import io
# --- ADICIONADO PARA O WEBOOK ---
from flask import Flask, request, jsonify 
app = Flask(__name__)
# ---------------------------------


# --- 1. CONFIGURAÇÃO E CREDENCIAIS ---

HOOKLAB_API_BASE_URL = "https://api.hooklab.com.br" 

# SEU TOKEN ATUALIZADO
# ATENÇÃO: É recomendado usar variáveis de ambiente para tokens em produção.
HOOKLAB_TOKEN ="eyJhbGciOiJIUzI1NiJ9.77-9GO-_vRY-77-977-9RO-_vRoCLRENGu-_vQ.K2POOyfuEkhWvfmAcr2OBWcXZb26bBA2nUxaDAvyQzk" 

HEADERS = {"access-token": HOOKLAB_TOKEN}

# ID de Status da Hooklab (Usado para filtro LOCAL)
VIOLATED_STATUS_ID = 6 

# Credenciais de E-mail
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "luissilva@madeiranit.com.br"
SMTP_PASS = "jszs tkzf nxgt napg"
RECIPIENT_EMAIL = "luissilva@madeiranit.com.br"
EMAIL_SENDER = "luissilva@madeiranit.com.br"

# --- 2. FUNÇÕES DE ACESSO À API E PROCESSAMENTO --

def fetch_all_paginated_data(endpoint: str) -> list:
    all_data = []
    limit = 100 
    offset = 0
    
    while True:
        url = f"{HOOKLAB_API_BASE_URL}{endpoint}"
        
        # AQUI está a única chamada API correta (com o timeout)
        response = requests.get(
            url, 
            headers=HEADERS, 
            params={"limit": int(limit), "offset": int(offset)},
            timeout=10 # Adiciona um limite de tempo de 10 segundos
        )
        
        if response.status_code != 200:
            print(f"❌ ERRO API no endpoint {endpoint}: {response.status_code} - {response.text}")
            break
            
        data = response.json()
        
        if not data.get('data'):
            break
            
        all_data.extend(data['data'])
        
        pagination = data.get('pagination', {})
        total = pagination.get('total', 0)
        
        if (offset + limit) >= total:
            break
            
        offset += limit
        
    return all_data


def send_email_report(subject: str, body: str, attachments: list):
    """Envia o e-mail com o corpo e anexos (planilhas)."""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = subject
    
    msg.attach(MIMEText(body, 'plain'))
    
    for filename, content in attachments:
        part = MIMEApplication(content, Name=filename)
        part['Content-Disposition'] = f'attachment; filename="{filename}"'
        msg.attach(part)
        
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_SENDER, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print(f"\n✅ Relatório(s) enviado(s) com sucesso para {RECIPIENT_EMAIL}")
    except Exception as e:
        print(f"\n❌ ERRO ao enviar e-mail: {e}")
        print("Verifique as credenciais SMTP (Usuário e Senha de Aplicativo/App Password).")


# --- 3. ROTA DO WEBOOK (Substitui a função main) ---
@app.route('/hooklab/report', methods=['POST'])
def handle_hooklab_report():
    
    # Recebe a chamada da Headffice ou outro serviço
    print(f"📦 Webhook recebido - Iniciando geração de relatórios: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    try:
        # 1. Busca todos os anúncios, sem filtro
        all_ads_data = fetch_all_paginated_data("/contract-offers")
        
        if not all_ads_data:
            print("\n❌ Falha ao buscar dados da API. Enviando e-mail de erro.")
            send_email_report(
                f"ERRO CRÍTICO Hooklab - {datetime.now().strftime('%d/%m/%Y %H:%M')}", 
                "Falha ao buscar dados da API da Hooklab. Verifique o token e a conexão.", 
                []
            )
            # Retorna um erro HTTP 500 para o serviço que chamou o webhook
            return jsonify({"status": "error", "message": "Falha ao buscar dados da API"}), 500

        # 2. FILTRAGEM CHAVE: APENAS VIOLADOS (ID 6).
        violated_ads = [
            ad for ad in all_ads_data 
            if ad.get('status', {}).get('id') == VIOLATED_STATUS_ID
        ]

        if not violated_ads:
            print("\n✅ Concluído: NENHUM anúncio violado foi encontrado. Enviando e-mail vazio.")
            send_email_report(
                f"Relatório Hooklab - {datetime.now().strftime('%d/%m/%Y %H:%M')}", 
                "Nenhum anúncio violado encontrado.", 
                []
            )
            # Retorna um sucesso HTTP 200
            return jsonify({"status": "success", "message": "Nenhum anúncio violado encontrado."}), 200
            
        final_ads_list = violated_ads
        
        # 3. Processa e agrupa os dados
        report_rows = []
        for ad in final_ads_list:
            company_name = ad.get('company', {}).get('name')
            seller_name = ad.get('seller', 'VENDEDOR_DESCONHECIDO')
            
            if company_name:
                group_name = company_name
            else:
                group_name = seller_name 
                
            row = {
                "Grupo de Responsabilidade": group_name,
                "Empresa Vinculada (API)": company_name if company_name else "SEM EMPRESA VINCULADA",
                "Seller Vinculado": seller_name,
                "Nome do Produto": ad.get('product', {}).get('title'),
                "Anúncio": ad.get('offer_link'),
                "Preço Anunciado": ad.get('prices', {}).get('price'),
                "Preço Permitido (PMA)": ad.get('status', {}).get('min_price'),
                "Status Detalhado": ad.get('status', {}).get('description'),
                "Em Estoque": "Sim" if ad.get('availability', {}).get('has_stock') is True else "Não"
            }
            report_rows.append(row)
            
        df_all_ads = pd.DataFrame(report_rows)
        grouped_reports = df_all_ads.groupby("Grupo de Responsabilidade")

        email_body_list = ["Olá, segue abaixo o resumo dos anúncios violados (independentemente do estoque). Há uma planilha em anexo para cada Grupo/Empresa responsável:", ""]
        email_attachments = []
        
        for group_name, df_group in grouped_reports:
            
            # 4. Gera o arquivo Excel em memória
            filename_safe = group_name.replace(' ', '_').replace('/', '_').replace(':', '')
            filename = f"{filename_safe}_Anuncios_Violados.xlsx"
            
            excel_buffer = io.BytesIO()
            df_group.to_excel(excel_buffer, index=False, engine='xlsxwriter')
            excel_buffer.seek(0)
            
            email_attachments.append((filename, excel_buffer.read()))

            # 5. Monta o corpo do e-mail
            email_body_list.append("-" * 80)
            email_body_list.append(f"GRUPO: {group_name}")
            email_body_list.append(f"  - Total de Anúncios Violados: {len(df_group)}")
            email_body_list.append(f"  - Sellers Distintos no Grupo: {df_group['Seller Vinculado'].nunique()}")
            email_body_list.append(f"  - Planilha em anexo: {filename}")
            email_body_list.append("-" * 80)
            
        # 6. Envia o e-mail final
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
        subject = f"Relatório Hooklab - Anúncios Violados (PMA) - {timestamp}"
        final_body = "\n".join(email_body_list)
        
        send_email_report(subject, final_body, email_attachments)

        # Retorna sucesso para o serviço que chamou o webhook
        return jsonify({"status": "success", "message": f"Relatório gerado e enviado para {RECIPIENT_EMAIL}"}), 200

    except Exception as e:
        print(f"❌ ERRO CRÍTICO NO WEBOOK: {e}")
        # Retorna erro interno HTTP 500
        return jsonify({"status": "error", "message": f"Erro interno do servidor: {str(e)}"}), 500


# --- 4. INICIALIZAÇÃO DO SERVIDOR (APENAS PARA TESTE LOCAL) ---
if __name__ == "__main__":
    print("Iniciando servidor Flask. Aguardando chamadas POST na rota /hooklab/report")
    # O Gunicorn (no Render) IGNORA este bloco, ele é só para teste no seu PC.
    app.run(host='0.0.0.0', port=5000, debug=True)

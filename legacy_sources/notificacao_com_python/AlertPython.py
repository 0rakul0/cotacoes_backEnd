import requests
import smtplib
import email.message
cotacao = "mxrf11"
# api
requisicao = requests.get(f'https://cotacaopython.herokuapp.com/cotacao/{cotacao}')
requisicao_dict = requisicao.json()
requisicao_info = requisicao_dict['VALOR_COTA']
requisicao_rendimento = requisicao_dict['RENDIMENTO']
requisicao_historico = requisicao_dict['HISTORICO']

print(requisicao_info)
print(requisicao_rendimento)
print(requisicao_historico)

# enviando por whatsapp

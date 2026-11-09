from unicodedata import normalize
from decimal import Decimal
import difflib,re
from datetime import datetime

def sao_iguais(parent,item,ratio=0.8):
    return difflib.SequenceMatcher(None,parent,item).ratio() >= ratio

def remove_sub_str(parent,item):
    array_parent = parent.split()
    array_item = item.split()
    total_porcentual = 0
    i= 0
    for word_item in array_item:
        porcentual_igualdade = difflib.SequenceMatcher(None,array_parent[0], word_item).ratio()
        total_porcentual = total_porcentual + porcentual_igualdade
        i = i + 1
        if porcentual_igualdade > 0.7 or (porcentual_igualdade > 0.5 and total_porcentual/i > 0.8) :
            array_parent.remove(array_parent[0])
    result = ""
    for word_parent in array_parent:
        result = result + word_parent + " "
    return result.strip()

def remove_acentos(txt):
    if not txt:
        return txt
    text = str((normalize('NFKD', txt).encode("ascii",errors="ignore")).decode("utf-8",errors="ignore"))
    return text.replace("'","").replace('"',"")

def remove_varios_espacos(txt):
    array = txt.split()
    return " ".join(array).strip()

def remove_caracteres_csv(txt):
    return txt.replace(',', ' ').replace(';', ' ').replace('\"', ' ').replace('\'', ' ')

def range_da_semana(ano,semana):
    data = str(ano)+'_'+str(semana)+'_'
    inicio = datetime.strptime(data+'1','%W_%Y_%w').strftime('%d/%m/%Y')
    final = datetime.strptime(data+'0','%W_%Y_%w').strftime('%d/%m/%Y')
    return inicio, final

def remove_tracos_pontos_barras_espacos(txt):
    return txt.replace('.','').replace('-','').replace('/','').replace(' ','')

def possui_numeros(inputString):
    return any(char.isdigit() for char in inputString)

def remove_espaco_e_pontuacao(txt):
    return remove_pontuacao(txt).replace(' ','')

def remove_parenteses(txt):
    return txt.replace('(','').replace(')','')

def remove_parenteses_e_pontuacao(txt):
    return remove_pontuacao(remove_parenteses(txt))

def remove_pontuacao(txt):
    return txt.replace(',', '').replace(';', '').replace('\"', '').replace('\'', '').replace('.','').replace('-','').\
        replace('/','').replace('?','').replace('$','').replace('!','').replace('—','').replace('–','').replace(':','').replace('\\','')

def extrai_decimal(input):
    str = input
    if "," in str:
        str = str.replace(".","")
        str = str.replace(",",".")
    result = 0.0
    for i in str:
        if not i.isdigit() and not i == ".":
            str = str.replace(i,"")
    result = Decimal(str.strip())
    return result

def remove_links(linha):
    linha = re.sub('\<.*?\>','',linha)
    linha = re.sub('([-a-zA-Z0-9@:%_\+.~#?&\/=]*)[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&\/=;]*)','',linha)

    return linha.strip()

def replace_last(source_string, replace_what, replace_with):
    head, sep, tail = source_string.rpartition(replace_what)
    return head + replace_with + tail

def remove_quebras_linha_de_linha(texto):
    return texto.replace('\n', ' ').replace('\r', '').strip()


def iniciais_palavra(palavra):
    iniciais = []
    palavra = remove_varios_espacos(palavra).upper().strip()
    for parte in palavra.split(' '):
        parte = parte.strip()

        if parte != '':
            iniciais.append(parte[0])
    return iniciais

def encontra_primeira_letra(s):
    i = re.search("[A-Za-z]", s, re.IGNORECASE)
    return -1 if i == None else i.start()


def remove_caracteres_especiais(nome):
    nome_corrigido = nome
    nome_corrigido = re.sub('[\\\/,;<>\.\?\/\!\*\-\+\_\=\@\#%:\(\)'']+', '', nome_corrigido)
    nome_corrigido = re.sub('\(\)', '', nome_corrigido)
    nome_corrigido = re.sub('\s{2,}', ' ', nome_corrigido)
    nome_corrigido = re.sub('^\s+', '', nome_corrigido)
    nome_corrigido = re.sub('\s+$', '', nome_corrigido)
    return nome_corrigido

def remove_caracteres_especiais_para_quadro(nome):
    nome_corrigido = nome
    nome_corrigido = re.sub('\s{2,}', ' ', nome_corrigido)
    nome_corrigido = re.sub('^\s+', '', nome_corrigido)
    nome_corrigido = re.sub('\s+$', '', nome_corrigido)
    return nome_corrigido


def acerta_valor_string_para_decimal(valor):
    if not valor[-1].isdigit() :
        valor = valor[:-1]
    ultimo_ponto = valor.rfind('.')
    ultima_virgula = valor.rfind(',')
    ultimo_digito = max(ultima_virgula,ultimo_ponto)
    inteiro = valor[:ultimo_digito]
    centavos = valor[ultimo_digito+1:]
    inteiro = inteiro.replace('.','').replace(',','')
    return Decimal(inteiro+'.'+centavos)

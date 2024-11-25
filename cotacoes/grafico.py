import os
from datetime import datetime
import numpy as np
import pandas as pd
from fastapi import HTTPException
import plotly.express as px
import plotly.graph_objects as go

def gerar_grafico_html(ticker: str, local=None) -> str:
    """Gera um gráfico interativo com plotly e retorna o HTML ou salva localmente."""
    # Define o caminho do arquivo baseado no ticker
    dia = datetime.today().strftime("%d-%m-%Y")
    if local:
        arquivo = f"../dados/csv/{dia}/stock_data_{str(ticker).split(':')[0]}.csv"
    else:
        arquivo = f"./dados/csv/{dia}/stock_data_{str(ticker).split(':')[0]}.csv"

    if not os.path.exists(arquivo):
        raise HTTPException(status_code=404, detail="Dados para o ticker não encontrados.")

    # Lê os dados do arquivo CSV
    df = pd.read_csv(arquivo)
    df["Valor"] = pd.to_numeric(
        df["Valor"].str.replace(".", "").str.replace(",", ".").str.replace("R$", ""),
        errors='coerce'
    )
    df.dropna(subset=["Valor"], inplace=True)
    df["Data_minute"] = pd.to_datetime(df["Data_minute"], errors='coerce')

    if df.empty:
        raise HTTPException(status_code=404, detail="Dados insuficientes para gerar o gráfico.")

    # Ordena os dados por Data_minute (caso necessário)
    df.sort_values(by="Data_minute", inplace=True)

    # Cria o gráfico interativo
    fig = px.line(df, x="Data_minute", y="Valor", title=f"Variação dos Preços de {ticker}")
    fig.update_layout(
        xaxis_title="Data e Hora",
        yaxis_title="Preço Médio (R$)",
        title_font=dict(size=18),
        xaxis_tickangle=45
    )

    # Adiciona linhas de máxima, mínima e tendência
    max_val = df["Valor"].max()
    min_val = df["Valor"].min()
    fig.add_hline(y=max_val, line_dash="dash", line_color="green", annotation_text=f"Máxima: {max_val:.2f}")
    fig.add_hline(y=min_val, line_dash="dash", line_color="red", annotation_text=f"Mínima: {min_val:.2f}")

    # Adiciona linha de tendência
    if len(df) > 1:
        x_numeric = (df["Data_minute"] - df["Data_minute"].min()).dt.total_seconds()
        coef = np.polyfit(x_numeric, df["Valor"], 1)
        tendencia = np.poly1d(coef)
        df["Tendencia"] = tendencia(x_numeric)
        fig.add_trace(
            go.Scatter(
                x=df["Data_minute"],
                y=df["Tendencia"],
                mode="lines",
                name="Tendência",
                line=dict(dash="dash", color="orange")
            )
        )

    # Salva o gráfico localmente se `local` for fornecido
    if local:
        # Se `local` for um caminho específico, use-o; caso contrário, crie um padrão
        if isinstance(local, str):
            output_path = local
        else:
            output_path = f"./graficos/{ticker}.html"

        # Garante que o diretório exista
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Salva o gráfico
        fig.write_html(output_path)
        print(f"Gráfico salvo em: {output_path}")

    # Converte o gráfico para HTML
    html = fig.to_html(full_html=False)
    return html

if __name__ == "__main__":
    # Salva o gráfico no diretório padrão
    gerar_grafico_html("BTC-BRL", True)

import statistics as st
import matplotlib.pyplot as plt

preco = [10.17, 10.25, 9.98, 9.91, 10.27, 10.37]
historico = [0.11,0.12,0.126,0.13,0.135,0.14]

print(st.mean(historico))
print(st.median(historico))
print(st.mode(historico))
print(st.stdev(historico))
print(st.pstdev(historico))

plt.plot(historico, preco)
plt.title("variação de preço")
plt.xlabel("proventos")
plt.ylabel("valor_ação")
plt.show()
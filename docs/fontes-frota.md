# Fontes dos números da frota e das coordenadas (Parte B, entrega de 07/10)

**Autora:** Beatriz · **Itens do kickoff:** C2 (fontes da frota) e A3 (unidades reais do sp_40)
**Como ler:** ✅ coerente com a fonte · ⚠️ a fonte sugere ajuste (decisão do grupo, **não alterei o YAML**) · ❌ sem fonte encontrada.
Fontes de segunda mão (blogs e sites de ficha técnica) estão marcadas; o ideal para o relatório é trocá-las pela ficha oficial do fabricante.

## 1. Modelos de referência (para ancorar os números)
| Tipo | Referência | Por quê |
|---|---|---|
| Moto | Honda CG 160 (versão Cargo) | moto mais usada em entregas (citada na fonte de custo de motoboy) |
| Carro | Fiat Argo 1.0 | hatch popular, com ficha e custo de manutenção publicados |
| Van | Fiat Fiorino furgão | furgão compacto mais comum em entrega urbana |

## 2. Parâmetros da frota (`configs/frota.yaml`)

| Parâmetro | Valor atual | O que a fonte diz | Situação |
|---|---|---|---|
| **Moto** capacidade 15 kg / 40 L | 15 / 40 | nenhuma fonte encontrada para o baú | ❌ |
| Moto autonomia | 120 km | tanque de 16,1 L e "até 660 km" com gasolina (560 km com etanol) [1]; motoboy roda ≈130 km por dia útil [2]. Então 120 km funciona como **limite operacional por jornada**, não como autonomia física | ✅ (renomear no relatório: "limite de km por jornada") |
| Moto velocidade 35 km/h | 35 | sem fonte direta; com o fator de pico de 1,4 cai para 25 km/h (CET: ver abaixo) | ✅ plausível, um pouco otimista |
| Moto R$/km | 0,80 | custo direto ≈ R$ 0,48/km: combustível 0,15 (40 km/L a R$ 6,17/L) + revisões 0,07 + depreciação 0,26 [2]. Não inclui pneus, seguro nem remuneração | ✅ (acima do custo direto, cobre o que falta) |
| Moto fixo/dia | R$ 60 | sem fonte (a fonte [2] só traz custos mensais de alimentação, celular, seguro) | ❌ |
| **Carro** capacidade 150 kg / 400 L | 150 / 400 | porta-malas do Argo: 300 L [3]; 150 kg é premissa operacional | ⚠️ 400 L > 300 L do Argo |
| Carro autonomia | 300 km | tanque 48 L; 13,9 km/L (gasolina, cidade, Inmetro) e 9,9 km/L (etanol) [3] → 475 a 667 km | ✅ (conservador) |
| Carro velocidade 28 km/h | 28 | com fator de pico 1,4 → 20 km/h; CET: 17,9 km/h (pico manhã) e 15,1 (pico tarde) em 2019 [6] | ✅ |
| Carro R$/km | 1,50 | combustível ≈ 0,46; custo de rodar ≈ 1,33 sem estacionamento/pedágio/lavagem; 1,94 com tudo (12.000 km/ano) [4] | ✅ dentro da faixa 1,33–1,94 |
| Carro fixo/dia | R$ 120 | sem fonte | ❌ |
| **Van** capacidade 800 kg / 3000 L | 800 / 3000 | Fiorino: carga útil 650 kg; compartimento 3.100 L [5a] ou 3.345 L [5b] | ⚠️ 800 kg > 650 kg; 3000 L ✅ |
| Van autonomia | 400 km | tanque 55 L; 11,7 km/L (G) e 8,1 km/L (A) [5b] → 446 a 644 km (assumindo G = gasolina e A = etanol; a página não explica) | ✅ (conservador) |
| Van velocidade 24 km/h | 24 | com fator de pico → 16 a 17 km/h, na faixa da CET | ✅ |
| Van R$/km | 2,50 | sem fonte. A tabela de frete da ANTT [7] é para carga rodoviária (fórmula distância × CCD + CC) e não traz coeficiente para veículo leve urbano | ❌ |
| Van fixo/dia | R$ 200 | sem fonte | ❌ |
| Fator de trânsito (1,4 manhã / 1,5 tarde) | 1,4 / 1,5 | CET: velocidade média cai de ~24,8 km/h (2018) para 17,9 (2019) no pico da manhã e de 18,5 para 15,1 no pico da tarde; série 2015-2019 [6]. O relatório da CET de 2024 só traz índice de lentidão, não km/h [8] | ✅ ordem de grandeza (dado mais recente por velocidade é 2019) |

### Pontos que merecem decisão do grupo (propostas, nada foi alterado)
1. **Van:** se a referência for a Fiorino, usar **650 kg / 3100 L**. Se quiserem 800 kg, citar outro modelo (não encontrei fonte).
2. **Carro:** se a referência for o Argo, usar **300 L**.
3. **Possível dupla contagem de custo:** o fitness soma R$/km **e** custo fixo por dia. O valor de 1,50 R$/km do carro já inclui depreciação, seguro e IPVA (que são fixos). Sugestão: R$/km só com custo variável (combustível + manutenção, ≈ 0,6 no carro) e o fixo/dia com depreciação + seguro + condutor. Isso mexe no peso relativo de "usar mais um veículo" × "rodar mais km", então é decisão do Conrado (spec 03).
4. **Autonomia** é um limite operacional por jornada, não o alcance do tanque (que sobra em todos os tipos). Em rotas de até ~100 km a restrição de autonomia quase nunca vai ativar; vale dizer isso no relatório.
5. **Sem fonte:** custo fixo/dia dos três tipos e R$/km da van. Se ninguém achar, o relatório deve declarar esses valores como premissas.

## 3. Coordenadas das 10 unidades reais (sp_40)
Fonte das coordenadas: IBGE, via página do CEP em ruacep.com.br [9], e Wikipédia (infobox) para o complexo do HC [10]. Parte são **centroides de CEP/rua** (precisão de algumas centenas de metros) e parte foi ajustada à mão no Google Maps (ver tabela); unidades dentro do mesmo complexo ficam com o mesmo ponto (distância 0 entre elas).

| # | Unidade | Endereço | Lat, Lon usados | Origem |
|---|---|---|---|---|
| 1 | InCor | Av. Dr. Enéas de Carvalho Aguiar, 44 | -23.55695, -46.66814 | ajustada no Google Maps (Beatriz, 14/10) |
| 2 | ICESP | Av. Dr. Arnaldo, 251 | -23.55591, -46.66817 | ajustada no Google Maps (Beatriz, 14/10) |
| 3 | IPq HC-FMUSP | R. Dr. Ovídio Pires de Campos, 785 | -23.55906, -46.67080 | ajustada no Google Maps (Beatriz, 14/10) |
| 4 | Instituto da Criança (ICr) | Av. Dr. Enéas de Carvalho Aguiar, 647 | -23.55552, -46.67318 | CEP 05403-000 | ajustada no Google Maps (Beatriz, 14/10) |
| 5 | HU-USP | Av. Prof. Lineu Prestes, 2565 | -23.56494, -46.74057 | ajustada no Google Maps (Beatriz, 14/10) |
| 6 | Hospital Auxiliar de Cotoxó | R. Cotoxó, 1142 | -23.53617, -46.68823 | CEP 05021-001 (trecho 709 ao fim) | ajustada no Google Maps (Beatriz, 14/10) |
| 7 | IMREA Lapa | R. Guaicurus, 1274 | -23.52162, -46.69779 | CEP 05033-002 (trecho 1001 ao fim) | ajustada no Google Maps (Beatriz, 14/10) |
| 8 | IOT HC-FMUSP | R. Dr. Ovídio Pires de Campos, 333 | -23.55782, -46.67117 | ajustada no Google Maps (Beatriz, 14/10) |
| 9 | Instituto de Radiologia (InRad) | R. Dr. Ovídio Pires de Campos | -23.55660, -46.67050 | ajustada no Google Maps (Beatriz, 14/10) |
| 10 | Instituto Central (ICHC) | Av. Dr. Enéas de Carvalho Aguiar, 255 | -23.55771, -46.66892 | ajustada no Google Maps (Beatriz, 14/10) |
| — | **Depósito** (Farmácia Central, HC-FMUSP) | complexo HC | -23.55770, -46.66893 | ajustada no Google Maps (Beatriz, 14/10) |

**Mudanças em relação ao que foi para o PR de 02/10:** (a) o ICESP estava ~1 km fora do lugar e foi corrigido (e depois ajustado no Google Maps); (b) as três "UBS de referência" que eu tinha incluído **não eram unidades verificadas** e foram trocadas por unidades reais do HC (Cotoxó, IMREA Lapa, Instituto Central); (c) o depósito passou a usar a coordenada do complexo. Por isso `sp_15`, `sp_40` e `sp_80` mudaram: resultados e relatórios gerados antes (por exemplo `reports/comparativo-s1`) foram calculados nas instâncias antigas.

**Conferência:** as coordenadas obtidas por CEP foram conferidas manualmente no Google Maps por Beatriz em 14/10/2026. Todas foram ajustadas.

**Distância ao depósito:** 7 das 10 unidades estão no próprio complexo do HC (de 0,1 a 0,4 km do depósito), o que é realista, mas faz essas entregas custarem quase nada de rota; o desafio de otimização vem dos domicílios sintéticos (média ≈ 13 km contra ≈ 1,6 km das 10 unidades; HU-USP 7,3 km, Lapa 4,9 km, Cotoxó 3,0 km). O `sp_15` usa InCor, ICESP, IPq e ICr (todas a menos de 0,4 km do depósito); espalhá-lo exigiria ajustar os testes do módulo LLM, que citam esses nomes.

## 4. Referências
1. Honda CG 160 Cargo 2022 (tanque, autonomia): <https://www.motoragora.com.br/?p=34647> *(site de notícias; ideal trocar pela ficha da Honda)*
2. Custos de um motoboy (combustível, revisões, depreciação, km/dia): <https://autopapo.com.br/motos/quanto-custa-ser-um-motoboy-no-brasil/> *(blog; estimativas do autor)*
3. Fiat Argo 1.0 (tanque, consumo Inmetro, porta-malas): <https://garagem360.com.br/hatch-da-fiat-cai-para-r-60-mil-e-faz-151-kml-na-estrada/> *(site de notícias)*
4. Custo de manter um Argo (por km): <https://www.zuldigital.com.br/blog/quanto-custa-manter-um-carro/> *(estimativa, ago/2025, 12.000 km/ano, gasolina a R$ 6,06/L)*
5. Fiorino: (a) <https://seminovos.localiza.com/blog/posts/capacidade-de-carga-da-fiorino> (650 kg, ~3.100 L); (b) <https://www.fichacompleta.com.br/carros/fiat/fiorino-furgao-endurance-1-4-2025> (tanque 55 L, consumo, 3.345 L; o próprio site avisa que pode ter erros)
6. CET, velocidade média no trânsito de SP, 1980-2019 (Relatório de Desempenho do Sistema Viário Principal, compilado pela SMUL): <https://drive.prefeitura.sp.gov.br/cidade/secretarias/upload/chamadas/12_velocidade_media_no_transito_1980_2019_1619113114.htm>
7. Piso mínimo de frete ANTT (Resolução 6.076/2026, em vigor desde 20/01/2026; fórmula distância × CCD + CC): <https://simplifique.contmatic.com.br/blogs/como-consultar-e-calcular-tabela-frete-antt-2026> *(coeficientes oficiais na calculadora da ANTT; não se aplicam a entrega urbana leve)*
8. CET, Relatório Administrativo 2024 (lentidão, sem km/h): <https://cetsp.com.br/media/1618397/relatorioadm2024_consolidado.pdf>
9. Coordenadas IBGE por CEP: <https://www.ruacep.com.br/sp/sao-paulo/cerqueira-cesar/05403901-avenida-doutor-eneas-carvalho-de-aguiar-647/> (e as páginas dos CEPs 05403-900, 05403-010, 01246-000, 05508-000, 05021-001, 05033-002 no mesmo site)
10. Complexo do HC (coordenadas): <https://en.wikipedia.org/wiki/Hospital_das_Cl%C3%ADnicas_da_Universidade_de_S%C3%A3o_Paulo>

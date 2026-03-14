import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="DCP-RECON Web", page_icon="🛰️")

st.title("🛰️ SISTEMA DCP-RECON v3.0")

# --- CONEXÃO COM GOOGLE SHEETS (VERSÃO CORRIGIDA) ---
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Pega os segredos e limpa as quebras de linha da chave privada
    creds_dict = st.secrets["gcp_service_account"].to_dict()
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# --- INTERFACE LATERAL ---
st.sidebar.header("Configurações")
raio_km = st.sidebar.slider("Raio de Busca (KM)", 1, 50, 15)
planilha_grupos = st.sidebar.text_input("Nome Planilha Grupos", "DCP_Grupos")
planilha_respostas = st.sidebar.text_input("Nome Planilha Respostas", "DCP_Respostas")

# --- BOTÃO PRINCIPAL ---
if st.button("🔍 PROCESSAR NOVO CANDIDATO"):
    with st.spinner("Conectando e Calculando..."):
        try:
            gc = conectar_google()
            
            # Carregar dados
            df_grupos = pd.DataFrame(gc.open(planilha_grupos).sheet1.get_all_records())
            df_candidatos = pd.DataFrame(gc.open(planilha_respostas).sheet1.get_all_records())
            
            if df_candidatos.empty:
                st.error("A planilha de respostas está vazia!")
            else:
                cand = df_candidatos.iloc[-1]
                st.write(f"### Analisando: {cand['Nome Completo']} ({cand['Perfil']})")
                
                geolocator = Nominatim(user_agent="dcp_recon_final")
                loc_cand = geolocator.geocode(cand['Endereço Completo'])
                
                if loc_cand:
                    ponto_cand = (loc_cand.latitude, loc_cand.longitude)
                    sugestoes = []

                    for _, grupo in df_grupos.iterrows():
                        # REGRA DE VAGAS
                        if int(grupo['Membros Atuais']) >= int(grupo['Capacidade Máxima']):
                            continue

                        # REGRA DE PERFIL
                        match = False
                        if cand['Perfil'] == "Casais" and grupo['Perfil'] == "Casais":
                            match = True
                        elif cand['Perfil'] in ["Homens", "Mulheres"]:
                            if grupo['Perfil'] == cand['Perfil'] or grupo['Perfil'] == "Misto":
                                match = True
                        elif cand['Perfil'] == "Misto" and grupo['Perfil'] == "Misto":
                            match = True
                        
                        if match:
                            loc_g = geolocator.geocode(grupo['Endereço'])
                            if loc_g:
                                d = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                                if d <= raio_km:
                                    sugestoes.append({"Grupo": grupo['Nome do Grupo'], "Dist": d, "Lider": grupo['Líder']})
                            time.sleep(1) # Respeita o GPS

                    if sugestoes:
                        top = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                        st.success(f"✅ Melhor opção: **{top['Grupo']}**")
                        st.info(f"📍 Distância: {top['Dist']:.2f} km | Líder: {top['Lider']}")
                    else:
                        st.warning("Nenhum grupo compatível encontrado no raio selecionado.")
                else:
                    st.error("Endereço do candidato não localizado.")
        except Exception as e:
            st.error(f"Erro: {e}")

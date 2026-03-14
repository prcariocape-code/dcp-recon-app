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

# --- CONEXÃO COM GOOGLE SHEETS ---
def conectar_google():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"].to_dict()
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    return gspread.authorize(creds)

# --- INTERFACE LATERAL ---
st.sidebar.header("Configurações")
raio_km = st.sidebar.slider("Raio de Busca (KM)", 1, 50, 15)
planilha_grupos = st.sidebar.text_input("Nome Planilha Grupos", "DCP_Grupos")
planilha_respostas = st.sidebar.text_input("Nome Planilha Respostas", "DCP_Respostas")

try:
    gc = conectar_google()
    # Carregar dados iniciais para o menu
    df_candidatos = pd.DataFrame(gc.open(planilha_respostas).sheet1.get_all_records())
    
    if not df_candidatos.empty:
        st.subheader("📋 Seleção de Candidato")
        # Criar menu de seleção com os nomes da planilha
        lista_nomes = df_candidatos['Nome Completo'].tolist()
        nome_selecionado = st.selectbox("Quem você deseja processar?", lista_nomes)
        
        # Filtrar apenas o candidato escolhido
        cand = df_candidatos[df_candidatos['Nome Completo'] == nome_selecionado].iloc[0]
        
        if st.button("🔍 ENCONTRAR MELHOR GRUPO"):
            with st.spinner(f"Calculando para {nome_selecionado}..."):
                df_grupos = pd.DataFrame(gc.open(planilha_grupos).sheet1.get_all_records())
                
                geolocator = Nominatim(user_agent="dcp_recon_v3")
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
                        perfil_c = str(cand['Perfil']).strip()
                        perfil_g = str(grupo['Perfil']).strip()

                        if perfil_c == "Casais" and perfil_g == "Casais":
                            match = True
                        elif perfil_c in ["Homens", "Mulheres"]:
                            if perfil_g == perfil_c or perfil_g == "Misto":
                                match = True
                        elif perfil_c == "Misto" and perfil_g == "Misto":
                            match = True
                        
                        if match:
                            loc_g = geolocator.geocode(grupo['Endereço'])
                            if loc_g:
                                d = geodesic(ponto_cand, (loc_g.latitude, loc_g.longitude)).km
                                if d <= raio_km:
                                    sugestoes.append({"Grupo": grupo['Nome do Grupo'], "Dist": d, "Lider": grupo['Líder']})
                            time.sleep(0.5)

                    if sugestoes:
                        top = sorted(sugestoes, key=lambda x: x['Dist'])[0]
                        st.success(f"✅ Melhor opção para **{nome_selecionado}**")
                        st.info(f"📍 Grupo: **{top['Grupo']}**\n\n📏 Distância: {top['Dist']:.2f} km\n\n👤 Líder: {top['Lider']}")
                    else:
                        st.warning("Nenhum grupo compatível encontrado no raio selecionado.")
                else:
                    st.error("Endereço do candidato não localizado pelo GPS.")
    else:
        st.warning("A planilha de respostas está vazia.")

except Exception as e:
    st.error(f"Erro de conexão ou de dados: {e}")

"""Campaigns page: Generate and approve promotional drafts."""
import streamlit as st

from database.repositories import ProductRepository, CampaignRepository
from models.campaign import Campaign, VALID_CAMPAIGN_STATUSES
from services.campaign_generator import generate_campaign

st.title("Campaigns")
st.caption("Generate promotional angles for your high-scoring products and manage their approval status.")

prod_repo = ProductRepository()
camp_repo = CampaignRepository()

# 1. Select a product
products = prod_repo.list_products()
if not products:
    st.info("No products found. Go to the Products page to add some first.")
    st.stop()

product_options = {f"{p.name} (Score: {p.opportunity_score or 'N/A'})": p for p in products}
selected_product_name = st.selectbox("Select a product to campaign:", list(product_options.keys()))
selected_product = product_options[selected_product_name]

st.divider()

# 2. Generate a new campaign draft
st.subheader("Generate New Draft")
col1, col2 = st.columns([2, 1])
with col1:
    angle = st.selectbox("Choose Promotional Angle:", ["Review", "Comparison", "Promo", "Story", "General"])
with col2:
    st.write("") # Spacer
    st.write("") # Spacer
    if st.button("Generate Draft", type="primary"):
        data = generate_campaign(selected_product.name, selected_product.merchant, angle)
        new_camp = Campaign(
            product_id=selected_product.id,
            campaign_type=data["type"],
            headline=data["headline"],
            body=data["body"]
        )
        camp_id = camp_repo.save_campaign(new_camp)
        try:
            prod_repo.add_observation(selected_product.id, "campaign_generation", f"Generated {data['type']} campaign.", selected_product.url, "high")
        except Exception: pass
        st.success(f"Draft generated and saved! (ID: {camp_id[:8]})")
        st.rerun()

st.divider()

# 3. List and manage existing campaigns
st.subheader(f"Drafts for: {selected_product.name}")
campaigns = camp_repo.list_campaigns_for_product(selected_product.id)

if not campaigns:
    st.info("No campaigns generated for this product yet.")
else:
    for camp in campaigns:
        with st.container(border=True):
            st.markdown(f"**{camp.headline}**")
            st.caption(f"Type: {camp.campaign_type} | Created: {camp.created_at:%Y-%m-%d}")
            st.write(camp.body)
            
            new_status = st.selectbox(
                "Status",
                VALID_CAMPAIGN_STATUSES,
                index=VALID_CAMPAIGN_STATUSES.index(camp.status),
                key=f"camp_status_{camp.id}",
                label_visibility="collapsed"
            )
            if new_status != camp.status:
                camp_repo.update_campaign_status(camp.id, new_status)
                st.rerun()
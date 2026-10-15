"""Campaigns page: Generate, approve, and publish promotional drafts."""
import streamlit as st

from database.repositories import ProductRepository, CampaignRepository
from models.campaign import Campaign
from services.campaign_generator import generate_campaign
from services.content_formatter import format_campaign

st.title("Campaigns")
st.caption("Generate promotional angles for your high-scoring products and manage their approval status.")

prod_repo = ProductRepository()
camp_repo = CampaignRepository()

products = prod_repo.list_products()
if not products:
    st.info("No products found. Go to the Products page to add some first.")
    st.stop()

product_options = {f"{p.name} (Score: {p.opportunity_score or 'N/A'})": p for p in products}
selected_product_name = st.selectbox("Select a product to campaign:", list(product_options.keys()))
selected_product = product_options[selected_product_name]

st.divider()

st.subheader("Generate New Draft")
col1, col2 = st.columns([2, 1])
with col1:
    angle = st.selectbox("Choose Promotional Angle:", ["Review", "Comparison", "Promo", "Story", "General"])
with col2:
    st.write(""); st.write("")
    if st.button("Generate Draft", type="primary"):
        data = generate_campaign(selected_product.name, selected_product.merchant, angle)
        new_camp = Campaign(product_id=selected_product.id, campaign_type=data["type"], headline=data["headline"], body=data["body"])
        camp_repo.save_campaign(new_camp)
        st.success("Draft generated!")
        st.rerun()

st.divider()

st.subheader(f"Drafts for: {selected_product.name}")
campaigns = camp_repo.list_campaigns_for_product(selected_product.id)

if not campaigns:
    st.info("No campaigns generated for this product yet.")
else:
    for camp in campaigns:
        with st.container(border=True):
            st.markdown(f"**{camp.headline}**")
            st.caption(f"Type: {camp.campaign_type} | Status: **{camp.status.upper()}**")
            st.write(camp.body)
            
            if camp.status == "draft":
                new_status = st.selectbox("Change Status", ["draft", "approved", "rejected"], key=f"status_{camp.id}")
                if new_status != camp.status:
                    camp_repo.update_campaign_status(camp.id, new_status)
                    st.rerun()
                    
            elif camp.status == "approved":
                st.success("✅ Approved for Publishing")
                with st.expander("📢 Publishing Studio"):
                    target_format = st.selectbox("Format", ["Blog Post", "Social Thread", "Newsletter"], key=f"fmt_{camp.id}")
                    formatted_content = format_campaign(camp.campaign_type, camp.headline, camp.body, target_format)
                    st.code(formatted_content, language="markdown")
                    
                    # Download button acts as the "Publish" action
                    if st.download_button(
                        label="Download & Publish",
                        data=formatted_content,
                        file_name=f"{camp.headline.replace(' ', '_')}.md",
                        mime="text/markdown",
                        key=f"pub_{camp.id}"
                    ):
                        camp_repo.publish_campaign(camp.id)
                        try:
                            prod_repo.add_observation(selected_product.id, "publication", f"Published as {target_format}.", selected_product.url, "high")
                        except Exception: pass
                        st.rerun()
                        
            elif camp.status == "published":
                st.info("🚀 Published. This asset is live in your records.")
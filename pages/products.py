"""Products page: submit, search, filter, and manage product status."""
import streamlit as st

from core.exceptions import ExtractionError, SSRFError
from database.repositories import ProductRepository
from models.product import (
    VALID_REVENUE_MODELS,
    VALID_STATUSES,
    Product,
    ProductValidationError,
)
from services.merchant_identifier import identify_merchant
from services.product_extractor import extract_product_data
from services.opportunity_scorer import calculate_opportunity_score

st.title("Products")
st.caption(
    "Submit a URL to automatically extract product details, identify the merchant, "
    "and save it permanently to your cloud database."
)

repo = ProductRepository()

with st.form("product_form", clear_on_submit=True):
    url = st.text_input("Product URL *", placeholder="https://example.com/product")
    manual_name = st.text_input("Manual name (optional - leave blank to auto-extract)")
    model = st.selectbox("Intended revenue model", VALID_REVENUE_MODELS, index=2)
    submitted = st.form_submit_button("Analyze & Save Product")

if submitted:
    try:
        product = Product(url=url, name="Processing...", revenue_model=model)
        merchant = identify_merchant(product.url)

        try:
            extracted = extract_product_data(product.url)
            final_name = manual_name.strip() if manual_name.strip() else extracted["title"]
            product.name = final_name
            product.merchant = merchant
            product.image_url = extracted.get("image_url")
            product_id = repo.add(product)
            try:
                repo.add_observation(
                    product_id, "extraction",
                    f"Automated extraction succeeded. Title: {final_name}",
                    product.url, "high",
                )
            except Exception as obs_exc:
                print(f"Observation save failed: {obs_exc}")
            st.success(f"Saved **{final_name}** ({merchant}) to the database.")
        except SSRFError as exc:
            st.error(f"Security block: {exc}")
        except ExtractionError as exc:
            st.warning(f"Extraction failed: {exc}. Saving with manual fallback.")
            fallback_name = manual_name.strip() if manual_name.strip() else "Manual Entry (Extraction Failed)"
            try:
                fallback_product = Product(url=url, name=fallback_name, revenue_model=model)
                fallback_product.merchant = merchant
                fallback_id = repo.add(fallback_product)
                try:
                    repo.add_observation(
                        fallback_id, "extraction_failure",
                        f"Automated extraction failed or was refused: {exc}",
                        fallback_product.url, "high",
                    )
                except Exception as obs_exc:
                    print(f"Observation save failed: {obs_exc}")
                st.info("Saved with manual fallback.")
            except Exception as save_exc:
                st.error("Could not save the product to the database. Technical details are in the server log.")
                print(f"Product save failed: {save_exc}")
    except ProductValidationError as exc:
        st.error(f"Please fix the input: {exc}")
    except Exception as exc:
        st.error("Could not save the product. Technical details are in the server log.")
        print(f"Product save failed: {exc}")

st.divider()
st.subheader("Saved products")

col_search, col_status = st.columns([2, 1])
with col_search:
    search = st.text_input("Search", key="product_search", placeholder="Search by name or URL")
with col_status:
    status_filter = st.selectbox(
        "Status filter", ["all"] + list(VALID_STATUSES), key="product_status_filter"
    )

try:
    products = repo.list_products(search=search, status=status_filter)
except Exception as exc:
    products = []
    st.error("Could not load products from the database. Technical details are in the server log.")
    print(f"Product list failed: {exc}")

if not products:
    st.info("No products match yet. Submit your first one above.")
else:
    for product in products:
        with st.container(border=True):
            c_img, c_info, c_status = st.columns([1, 3, 1])

            if product.image_url:
                c_img.image(product.image_url, width=100)
            else:
                c_img.markdown("📦")

            c_info.markdown(f"**{product.name}**")
            c_info.caption(product.url)
            c_info.caption(f"Model: {product.revenue_model} | Merchant: {product.merchant}")
            
            if product.opportunity_score is not None:
                if product.opportunity_score >= 70:
                    c_info.success(f"🏆 Score: {product.opportunity_score}/100")
                elif product.opportunity_score >= 40:
                    c_info.warning(f"📊 Score: {product.opportunity_score}/100")
                else:
                    c_info.error(f"📉 Score: {product.opportunity_score}/100")

            new_status = c_status.selectbox(
                "Status",
                VALID_STATUSES,
                index=VALID_STATUSES.index(product.status),
                key=f"status_{product.id}",
                label_visibility="collapsed",
            )
            if new_status != product.status:
                try:
                    repo.update_status(product.id, new_status)
                except Exception as exc:
                    st.error("Could not update the status. Technical details are in the server log.")
                    print(f"Status update failed: {exc}")
                st.rerun()
                
            c_score_btn, c_reasoning = st.columns([1, 4])
            if c_score_btn.button("Generate Score", key=f"score_btn_{product.id}"):
                has_data = bool(product.image_url and product.name != "Manual Entry (Extraction Failed)")
                score, reasoning = calculate_opportunity_score(product.merchant, product.revenue_model, has_data)
                try:
                    repo.update_score(product.id, score, reasoning)
                    try:
                        repo.add_observation(
                            product.id, "scoring",
                            f"Generated opportunity score: {score}/100",
                            product.url, "high"
                        )
                    except Exception:
                        pass
                except Exception as exc:
                    st.error("Could not save the score. Technical details are in the server log.")
                    print(f"Score save failed: {exc}")
                st.rerun()
                
            if product.score_reasoning:
                with st.expander("View Score Reasoning"):
                    for line in product.score_reasoning.split("\n"):
                        st.markdown(line)
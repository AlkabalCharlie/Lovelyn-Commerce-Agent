"""Products page: submit, search, filter, and manage product status."""
import streamlit as st

from database.repositories import ProductRepository
from models.product import (
    VALID_REVENUE_MODELS,
    VALID_STATUSES,
    Product,
    ProductValidationError,
)

st.title("Products")
st.caption(
    "Submit opportunities, search them, and manage their status. "
    "Everything is stored permanently in your Supabase database."
)

repo = ProductRepository()

with st.form("product_form", clear_on_submit=True):
    url = st.text_input("Product URL *", placeholder="https://example.com/product")
    name = st.text_input("Product name (optional)")
    model = st.selectbox("Intended revenue model", VALID_REVENUE_MODELS, index=2)
    submitted = st.form_submit_button("Save product")

if submitted:
    try:
        product = Product(url=url, name=name, revenue_model=model)
        product_id = repo.add(product)
        st.success(f"Saved to database (id {product_id[:8]}…).")
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
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.markdown(f"**{product.name}**")
            c1.caption(product.url)
            c2.caption(f"Model: {product.revenue_model}")
            if product.created_at:
                c2.caption(f"Added: {product.created_at:%Y-%m-%d %H:%M}")
            new_status = c3.selectbox(
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
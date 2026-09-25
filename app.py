from flask import Flask, render_template, request, redirect, session
from database import get_db_connection
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = "shopping_secret_key"


@app.route("/")
def home():
    return render_template("index.html")

@app.route("/products")
def products():

    search = request.args.get("search", "")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if search:

        cursor.execute(
            """
            SELECT * FROM products
            WHERE product_name LIKE %s
            """,
            ("%" + search + "%",)
        )

    else:

        cursor.execute("SELECT * FROM products")

    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "products.html",
        products=products,
        search=search
    )

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sql = "SELECT * FROM users WHERE email=%s AND password=%s"
        cursor.execute(sql, (email, password))

        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if user:
            session["user_id"] = user["user_id"]
            return redirect("/")
        else:
            return "Invalid Email or Password"

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()

        sql = """
        INSERT INTO users(full_name, email, password)
        VALUES (%s, %s, %s)
        """

        cursor.execute(sql, (full_name, email, password))
        conn.commit()

        cursor.close()
        conn.close()

        return redirect("/login")

    return render_template("register.html")

@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    user_id = session.get("user_id")
    quantity = 1

    # Product already in cart unda check cheyadam
    cursor.execute(
        "SELECT * FROM cart WHERE user_id=%s AND product_id=%s",
        (user_id, product_id)
    )

    item = cursor.fetchone()

    if item:
        cursor.execute(
            """
            UPDATE cart
            SET quantity = quantity + 1
            WHERE user_id=%s AND product_id=%s
            """,
            (user_id, product_id)
        )
    else:
        cursor.execute(
            """
            INSERT INTO cart(user_id, product_id, quantity)
            VALUES(%s,%s,%s)
            """,
            (user_id, product_id, quantity)
        )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

@app.route("/cart")
def cart():

    user_id = session["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    sql = """
    SELECT
        cart.cart_id,
        products.product_name,
        products.price,
        products.image,
        cart.quantity
    FROM cart
    JOIN products
    ON cart.product_id = products.id
    WHERE cart.user_id = %s
    """

    cursor.execute(sql, (user_id,))
    cart_items = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("cart.html", cart_items=cart_items)

@app.route("/remove_from_cart/<int:cart_id>")
def remove_from_cart(cart_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM cart WHERE cart_id=%s",
        (cart_id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

@app.route("/checkout")
def checkout():

    user_id = session["user_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Get cart items with product prices
    cursor.execute(
        """
        SELECT
            cart.product_id,
            cart.quantity,
            products.price
        FROM cart
        JOIN products
        ON cart.product_id = products.id
        WHERE cart.user_id = %s
        """,
        (user_id,)
    )

    cart_items = cursor.fetchall()

    # Check if cart is empty
    if not cart_items:
        cursor.close()
        conn.close()
        return "Your cart is empty!"

    # Calculate total amount
    total_amount = 0

    for item in cart_items:
        total_amount += item["price"] * item["quantity"]

    # Create new order
    cursor.execute(
        "INSERT INTO orders(user_id) VALUES(%s)",
        (user_id,)
    )

    conn.commit()

    order_id = cursor.lastrowid

    # Save cart items into order_items
    for item in cart_items:

        cursor.execute(
            """
            INSERT INTO order_items(order_id, product_id, quantity)
            VALUES(%s, %s, %s)
            """,
            (
                order_id,
                item["product_id"],
                item["quantity"]
            )
        )

    conn.commit()

    # Empty cart
    cursor.execute(
        "DELETE FROM cart WHERE user_id=%s",
        (user_id,)
    )

    conn.commit()

    cursor.close()
    conn.close()

    # Show order confirmation page
    return render_template(
        "checkout.html",
        order_id=order_id,
        total_amount=total_amount
    )
@app.route("/my_orders")
def my_orders():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.order_id,
            o.order_date,
            o.status,
            oi.quantity,
            p.id AS product_id,
            p.product_name,
            p.price,
            p.image
        FROM orders o
        JOIN order_items oi
            ON o.order_id = oi.order_id
        JOIN products p
            ON oi.product_id = p.id
        WHERE o.user_id = %s
        ORDER BY o.order_date DESC
    """, (session["user_id"],))

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("my_orders.html", orders=orders)

@app.route("/cancel_order/<int:order_id>")
def cancel_order(order_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Check order belongs to logged-in user
    cursor.execute("""
        SELECT order_id, status
        FROM orders
        WHERE order_id = %s
        AND user_id = %s
    """, (order_id, session["user_id"]))

    order = cursor.fetchone()

    if not order:
        cursor.close()
        conn.close()
        return "Order not found", 404

    # Cancel only Placed orders
    if order["status"] == "Placed":

        # Get products and quantities from this order
        cursor.execute("""
            SELECT product_id, quantity
            FROM order_items
            WHERE order_id = %s
        """, (order_id,))

        items = cursor.fetchall()

        # Restore product stock
        for item in items:

            cursor.execute("""
                UPDATE products
                SET quantity = quantity + %s
                WHERE id = %s
            """, (item["quantity"], item["product_id"]))

        # Change order status
        cursor.execute("""
            UPDATE orders
            SET status = 'Cancelled'
            WHERE order_id = %s
            AND user_id = %s
        """, (order_id, session["user_id"]))

        conn.commit()

    cursor.close()
    conn.close()

    return redirect("/my_orders")


@app.route("/increase_quantity/<int:cart_id>")
def increase_quantity(cart_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE cart
        SET quantity = quantity + 1
        WHERE @cart_id=%s
    """, (cart_id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

@app.route("/decrease_quantity/<int:cart_id>")
def decrease_quantity(cart_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT quantity
        FROM cart
        WHERE cart_id=%s
    """, (cart_id,))

    qty = cursor.fetchone()[0]

    if qty > 1:
        cursor.execute("""
            UPDATE cart
            SET quantity = quantity - 1
            WHERE cart_id=%s
        """, (cart_id,))
    else:
        cursor.execute("""
            DELETE FROM cart
            WHERE cart_id=%s
        """, (cart_id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/cart")

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

@app.route("/admin")
def admin():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Total Products
    cursor.execute("SELECT COUNT(*) AS total_products FROM products")
    total_products = cursor.fetchone()["total_products"]

    # Total Orders
    cursor.execute("SELECT COUNT(*) AS total_orders FROM orders")
    total_orders = cursor.fetchone()["total_orders"]

    # Total Users
    cursor.execute("SELECT COUNT(*) AS total_users FROM users")
    total_users = cursor.fetchone()["total_users"]

    # Total Sales
    cursor.execute("""
        SELECT COALESCE(SUM(oi.quantity * p.price), 0) AS total_sales
        FROM order_items oi
        JOIN products p
            ON oi.product_id = p.id
        JOIN orders o
            ON oi.order_id = o.order_id
        WHERE o.status != 'Cancelled'
    """)
    total_sales = cursor.fetchone()["total_sales"]

    # All Products
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin.html",
        products=products,
        total_products=total_products,
        total_orders=total_orders,
        total_users=total_users,
        total_sales=total_sales
    )

@app.route("/admin_orders")
def admin_orders():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            o.order_id,
            o.user_id,
            p.product_name,
            oi.quantity,
            p.price,
            (p.price * oi.quantity) AS total_amount,
            o.order_date
        FROM orders o
        JOIN order_items oi
            ON o.order_id = oi.order_id
        JOIN products p
            ON oi.product_id = p.id
        ORDER BY o.order_date DESC
    """)

    orders = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "admin_orders.html",
        orders=orders
    )
@app.route("/add_product", methods=["GET", "POST"])
def add_product():

    if request.method == "POST":

        product_name = request.form["product_name"]
        price = request.form["price"]
        quantity = request.form["quantity"]
        description = request.form["description"]

        image = request.files["image"]

        if image and image.filename:

            filename = secure_filename(image.filename)

            upload_folder = os.path.join(
                app.static_folder,
                "uploads"
            )

            os.makedirs(upload_folder, exist_ok=True)

            image.save(
                os.path.join(upload_folder, filename)
            )

        else:
            filename = None

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO products
            (product_name, price, quantity, image, description)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                product_name,
                price,
                quantity,
                filename,
                description
            )
        )

        conn.commit()

        cursor.close()
        conn.close()

        return redirect("/admin")

    return render_template("add_product.html")

@app.route("/edit_product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":

        product_name = request.form["product_name"]
        price = request.form["price"]
        quantity = request.form["quantity"]
        description = request.form["description"]

        image = request.files.get("image")

        # If new image is selected
        if image and image.filename != "":
            filename = image.filename
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            cursor.execute("""
                UPDATE products
                SET product_name=%s,
                    price=%s,
                    quantity=%s,
                    description=%s,
                    image=%s
                WHERE id=%s
            """, (
                product_name,
                price,
                quantity,
                description,
                filename,
                id
            ))

        else:
            # Keep old image
            cursor.execute("""
                UPDATE products
                SET product_name=%s,
                    price=%s,
                    quantity=%s,
                    description=%s
                WHERE id=%s
            """, (
                product_name,
                price,
                quantity,
                description,
                id
            ))

        conn.commit()

        cursor.close()
        conn.close()

        return redirect("/admin")

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "edit_product.html",
        product=product
    )
@app.route("/delete_product/<int:id>")
def delete_product(id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM products WHERE id=%s", (id,))

    conn.commit()

    cursor.close()
    conn.close()

    return redirect("/admin")

@app.route("/product/<int:product_id>")
def product_details(product_id):

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (product_id,)
    )

    product = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template(
        "product_details.html",
        product=product
    )

if __name__ == "__main__":
    app.run(debug=True)
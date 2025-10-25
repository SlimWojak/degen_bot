FROM nginx:alpine

# Copy the new professional dashboard files
COPY index.html /usr/share/nginx/html/index.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY app.js /usr/share/nginx/html/app.js
COPY nginx.conf /etc/nginx/nginx.conf

# Copy the Hyperliquid admin page
COPY public/hl_admin.html /usr/share/nginx/html/hl_admin.html

# Create logs directory
RUN mkdir -p /var/log/nginx

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

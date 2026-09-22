FROM nginx:alpine@sha256:54f2a904c251d5a34adf545a72d32515a15e08418dae0266e23be2e18c66fefa
RUN apk add --no-cache certbot certbot-nginx openssl
COPY nginx.conf /etc/nginx/nginx.conf
COPY snippets/ /etc/nginx/snippets/
COPY oauth-rate-limited.html /usr/share/nginx/html/oauth-rate-limited.html
EXPOSE 80 443

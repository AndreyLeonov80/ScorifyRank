FROM node:22-alpine

WORKDIR /app
COPY package.json ./
COPY package-lock.json* ./
RUN npm install

COPY scripts ./scripts
COPY css ./css
COPY scss ./scss
COPY js ./js
COPY src ./src
COPY *.html ./
COPY tsconfig.json ./
COPY vite.config.ts ./
COPY app.manifest.json ./
RUN npm run build

EXPOSE 8008
CMD ["npm", "run", "preview"]

# 建置階段
FROM node:20-alpine as build

WORKDIR /app

# 複製 package*.json
COPY package*.json ./

# 安裝依賴
RUN npm install

# 複製專案檔案
COPY . .

# 建置專案
RUN npm run build

# 執行階段
FROM nginx:alpine

# 從建置階段複製建置結果
COPY --from=build /app/build /usr/share/nginx/html

# 複製 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露連接埠
EXPOSE 80

# 啟動 nginx
CMD ["nginx", "-g", "daemon off;"] 
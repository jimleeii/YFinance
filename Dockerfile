# Build stage
FROM mcr.microsoft.com/dotnet/sdk:9.0 AS build
WORKDIR /src
COPY ["YFinance.sln", "."]
COPY ["src/YFinance.csproj", "src/"]
RUN dotnet restore "YFinance.sln"

# Copy all source files and build
COPY . .
WORKDIR "/src/src"
RUN dotnet build "YFinance.csproj" -c Release -o /app/build

# Publish stage
FROM build AS publish
RUN dotnet publish "YFinance.csproj" -c Release -o /app/publish

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:9.0 AS final
WORKDIR /app
COPY --from=publish /app/publish .
EXPOSE 8080
ENV ASPNETCORE_URLS=http://*:8080
ENTRYPOINT ["dotnet", "YFinance.dll"]
# Stage 1: Build the Go application
FROM golang:1.21-alpine AS builder
# Using Alpine for a smaller builder image. Adjust Go version if needed.

WORKDIR /app

# Copy module files and download dependencies first to leverage Docker cache
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the application source code
# Copy specific directories needed for the build
COPY server/ ./server/
COPY gen/go/ ./gen/go/
COPY game.proto ./game.proto # Proto file might be needed if referenced indirectly, safer to include
COPY map.txt ./map.txt # Map might be needed during build if state.go reads it differently, safer to copy

# Build the server application statically for Linux
# CGO_ENABLED=0 disables Cgo for static linking
# GOOS=linux ensures it's built for the Linux container environment (Alpine)
# -o specifies the output file path
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /server-app ./server/cmd/server/main.go

# Stage 2: Create the final minimal runtime image
FROM alpine:latest
# Using Alpine for a small runtime image size.

WORKDIR /app

# Copy the compiled application binary from the builder stage
COPY --from=builder /server-app /app/server-app

# Copy the map file needed at runtime
COPY --from=builder /app/map.txt /app/map.txt

# Expose the default port the server listens on (adjust if your default changed)
# This is documentation; you still need -p in 'docker run' to map it.
EXPOSE 50051

# Define the command to run the server
# Use 0.0.0.0 to listen on all interfaces inside the container
# Provide default port matching the EXPOSE directive
ENTRYPOINT ["/app/server-app"]
CMD ["-ip", "0.0.0.0", "-port", "50051"]

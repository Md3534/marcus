# Marcus Store

A Django-based e-commerce platform.

## Getting Started

This project is fully dockerized to ensure a seamless setup experience. You can run the entire application, including the database, using Docker.

### Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/)

### Running the Application (Docker)

1.  **Clone the repository** (if you haven't already).
2.  **Environment Variables**: Ensure you have a `.env` file in the root directory. This project already includes a development `.env` for easy onboarding.
3.  **Start the services**: Run the following command in the root of the project to build and start the containers.

```bash
docker-compose up --build
```

4.  **Access the application**: Once the containers are running and the database is ready, the application will be accessible at [http://localhost:8000](http://localhost:8000).

*Note: The `entrypoint.sh` script will automatically wait for the database to be ready, apply all database migrations, and then start the Django server.*

### Stopping the Application

To stop the running containers, press `Ctrl+C` in the terminal where Docker Compose is running, or run:

```bash
docker-compose down
```

To stop and remove all volumes (including your database data!):

```bash
docker-compose down -v
```

---

## Development & IDE Setup

For the best developer experience, we have included configuration for **Visual Studio Code (VSCode)**.

### VSCode Setup

1.  Open the project folder in VSCode.
2.  Install the recommended extensions when prompted (or check `.vscode/extensions.json`).
3.  The project includes settings for code formatting (`black`) and the Python interpreter.
4.  **Debugging**: You can easily run the application via VSCode's built-in debugger. Go to the "Run and Debug" panel (Ctrl+Shift+D or Cmd+Shift+D) and select either **"Python: Django"** (for local without docker) or **"Docker: Django"** to run the app directly from your IDE.

## Application Structure

*   `apps/` - Contains all Django applications (core, users, products, notifications).
*   `config/` - Main project configuration and routing.
*   `settings/` - Split settings (base.py, dev.py, prod.py).
*   `utils/` - Utility functions and helpers.

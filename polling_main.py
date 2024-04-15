from bot import build_application


def main():
    application = build_application()
    # use python thread to run a function to setup flask as the webserver
    application.run_polling()


if __name__ == "__main__":
    main()

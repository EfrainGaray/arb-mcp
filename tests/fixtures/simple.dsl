workspace "Simple" "A minimal Structurizr workspace" {
    model {
        user = person "User" "An end user"
        sys = softwareSystem "System" "The system" {
            web = container "Web App" "Serves the UI" "TypeScript"
        }
        user -> web "Uses" "HTTPS"
    }
    views {
        systemContext sys {
            include *
        }
    }
}

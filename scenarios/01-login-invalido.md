# Cenário 1 — Login com dados inválidos

## Objetivo do teste

Validar que a aplicação impede o login quando são informadas credenciais inválidas e apresenta a
mensagem de erro esperada.

## Passos

1. Acessar a aplicação: https://bugbank.netlify.app/
2. Localizar o campo "E-mail".
3. Informar o e-mail qualquerCoisa0001@gmail.com.
4. Localizar o campo "Senha".
5. Informar a senha Teste@123.
6. Clicar no botão "Acessar".
7. Validar que é apresentado um modal contendo a mensagem: "Usuário ou senha inválido. Tente novamente ou verifique suas informações!"

## Resultado esperado

O teste deve ser considerado aprovado quando o modal for apresentado e a mensagem esperada estiver
disponível na tela.

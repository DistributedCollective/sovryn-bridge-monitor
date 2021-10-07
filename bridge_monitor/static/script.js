$(document).ready(function() {
    $("time.timeago").timeago();

    $("a[data-vote-command]").click(function (e) {
        e.preventDefault();
        //alert(
        //    "Vote for this transaction by running this command in the sovryn-scripts repo:\n\n" +
        //    $(this).data('vote-command')
        //);
        $(this).after($(
            '<code class="vote-command">' +
            $(this).data('vote-command') +
            '</code>'
        ));
        $(this).replaceWith("<code style='color: #ccc'>Manually vote tx by running this in the sovryn-scripts repo:</code>")
    })
});

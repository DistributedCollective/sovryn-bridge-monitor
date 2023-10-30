$(document).ready(function() {
    $("time.timeago").timeago();

    $("a[data-vote-command]").click(function (e) {
        e.preventDefault();
        $(this).after($(
            '<code class="vote-command">' +
            $(this).data('vote-command') +
            '</code>'
        ));
        $(this).replaceWith("<code style='color: #ccc'>Manually vote tx by running this in the sovryn-scripts repo:</code>")
    })

    $("a.show-detail-transactions").each(function () {
        var $this = $(this);
        var detailsCurrentlyShown = false;
        var showText = $this.text();
        var hideText = showText.replace('show', 'hide');
        var detailId = $this.data('detail-id');
        var $wrapper = $('[data-detail-id="' + detailId + '"].detail-transactions-wrapper');
        $this.click(function(e) {
            e.preventDefault();
            if (detailsCurrentlyShown) {
                $wrapper.hide();
                $this.text(showText);
                detailsCurrentlyShown = false
            } else {
                $wrapper.show();
                $this.text(hideText);
                detailsCurrentlyShown = true
            }
        });
    })
});
